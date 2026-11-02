# Fast Entry App — AGENTS.md

## Scope
Fast Entry desk pages + ERPNext form overrides for Sales/Purchase Invoice / Quotation.
App module: `fast_entry_app`. Lives at `apps/fast_entry_app/`.

## Latest change: Sales Invoice numbering = `<ABBR>/000001/<YY-YY>` (restarts every FY)
**Goal:** Sales Invoice numbers look like `GC/000001/26-27`, restart at `000001` each financial year, and stay within India Compliance's 16-character GST invoice-number limit (which also fixes "Invalid GST Transaction Name" when creating invoices from the normal ERPNext form).

### Why a custom `autoname()`
Frappe derives the `tabSeries` counter key from the text rendered **before** the number. Because the financial year sits **after** the number here, a stock `naming_series` template (`GC/.######./26-27`) would key the counter on `GC/` and keep counting across years. So the DocType autoname stays `naming_series:` (Frappe still handles amendments/prompts) and `SalesInvoice.autoname()` fills `name` first.

### Implementation
- `overrides/naming.py` (new):
  - `fiscal_year_short(date, company)` → `26-27` from the Fiscal Year record (`get_fiscal_year(..., raise_on_missing=False)`).
  - `invoice_series(doc)` → `("GC/26-27/", "GC/.######./26-27")`; uses `posting_date` (fallback `transaction_date`).
  - `make_invoice_number(doc)` → `GC/000001/26-27` via `getseries(counter_key, 6)`; sets `doc.naming_series` to the FY template; warns (non-blocking) when the number exceeds 16 chars.
  - No-FY fallback: resets `naming_series` to `SINV-.YY.-` so the stock path can never hand out a number our per-FY counter later reuses.
  - `sync_invoice_series_options()` → regenerates the `Sales Invoice.naming_series` Property Setter options from current companies + current FY, plus legacy series; pins `Amended Document Naming Settings` for Sales Invoice to `Default Naming`.
- `overrides/controllers.py`: `SalesInvoice.autoname()` calls `make_invoice_number`, falls back to `naming_series` when the company abbr / FY cannot be resolved.
- `install.py`: `_setup_invoice_series()` added to `after_install()` (try/except, never breaks install); runs on `after_migrate` too, so sites converge on the next migrate.
- `api/sales.py`: the hardcoded `si.naming_series = "SINV-.YY.-"` is removed — numbering now derives from company + fiscal year for Fast Entry invoices too.

### Gotchas
- **16-char GST limit**: `GC/000001/26-27` = 15 chars, `GOC/…`/`GGE/…` = 16 (at the limit) → any company abbreviation longer than **3 characters** produces a GST-invalid invoice number.
- Amendments must take a **fresh** number; Frappe's default `Amend Counter` appends `-1` → `GC/000001/26-27-1` (17 chars) and is rejected, hence the `Default Naming` amendment rule.
- The dropdown options are **cosmetic**; `make_invoice_number()` is authoritative. A site without a Company (or before the FY is created) only gets the legacy options — re-run `bench --site <site> migrate` after creating the company/FY.
- New FY → option list refresh happens on migrate; numbers restart automatically because the counter key embeds the FY.

### Verification
- Naming suite `/tmp/opencode/test_naming.py` → 23 PASS / 0 FAIL (all rolled back): per-company counters (`GC` 000001/000002; `SA`/`GGE`/`GOC` each 000001), delete-draft keeps the gap, submit→cancel→amend yields a fresh number (no `-1`), Fast Entry invoice numbered `GC/000007/26-27`, and a date outside any FY falls back to `SINV-26-…`.

### Files touched
- `fast_entry_app/overrides/naming.py` (new), `fast_entry_app/overrides/controllers.py`, `fast_entry_app/install.py`, `fast_entry_app/api/sales.py`

## Latest change: lock `update_stock` on Fast Entry-created invoices
**Goal:** Stock ledger follows the Fast Entry setting and cannot be toggled after a Fast Entry invoice is created, while manual ERPNext invoices stay editable.

### Problem
Server only set `si.update_stock = 1` when enabled, never reset to `0`. The desk JS sends `update_stock: 0` when unchecked, but the server ignored `0`. Property Setter defaults the field to `1`.

### Fix (committed `4af78d6`)
- `api/sales.py` / `api/purchase.py`: server now forces `si.update_stock` / `pi.update_stock` to `1 if data.get("update_stock") else 0`, overriding the Property Setter default `1`.

### Client-side lock (this session)
- `public/js/erpnext_pi_override.js`:
  - New `lock_update_stock_on_fast_entry(frm)` — if `frm.doc.fe_dedup_key` is truthy, sets `update_stock` **read_only** via `frm.set_df_property("update_stock", "read_only", 1)`.
  - Wired into `frappe.ui.form.on("Sales Invoice", ...)` and `("Purchase Invoice", ...)` refresh handlers, after `default_update_stock(frm)`.
  - Fast Entry invoices are identified by `fe_dedup_key`; manual invoices (no key) stay fully editable.
- Loaded via `hooks.py` `doctype_js` for both "Sales Invoice" and "Purchase Invoice" (inlined into form meta → `bench clear-cache` suffices, no asset-version bump).

### Files touched
- `apps/fast_entry_app/fast_entry_app/public/js/erpnext_pi_override.js` (added `lock_update_stock_on_fast_entry` + 2 refresh-handler calls)
- `apps/fast_entry_app/AGENTS.md` (this file, new)

### Verification
- `node --check` on the JS file: OK.
- `bench --site dev.localhost clear-cache`: run.
- No DB migration needed (uses existing `fe_dedup_key` field + Property Setter default `1`).

## Latest change: batch tracking support (optional, sales + purchase)
**Goal:** Allow selecting/creating a batch number per item row in Fast Sales Entry and Fast Purchase Entry. Not mandatory, but required when the item is batch-tracked.

### API changes
- `api/item.py`:
  - `search_items` / `get_item_details` now return `has_batch_no`.
  - New `search_batches(item_code, warehouse, search, limit)` whitelisted endpoint returns batches (with available qty when warehouse given).
- `api/sales.py`: item row now sets `item_row.batch_no` from `item_data.batch_no` (must exist).
- `api/purchase.py`: item row sets `item_row.batch_no`; if the batch doesn't exist and the item is batch-tracked, creates it via `make_batch` (purchase receiving new stock can mint a new batch number).

### Desk pages (sales + purchase)
- Row object gains `batch_no` and `has_batch_no`.
- `render_row` adds a hidden `.fe-batch-input` text field below item code; shown when `has_batch_no`.
- `on_item_selected` sets `row.has_batch_no` from item details and toggles the field.
- `bind_row_events` wires batch autocomplete (search_batches) for both pages.
- `get_save_data` includes `batch_no` per item.

### PWA (`www/sales_pwa/index.html`)
- Item card gains a hidden `.batch-inp` text field; shown when `has_batch_no`.
- `onItemSelected` sets `row.has_batch_no`.
- `get_save_data` includes `batch_no`.

### HRMS (`FastEntryItems.vue` + `FastSalesEntry.vue`)
- Row gains `batchNo`/`hasBatchNo`; batch input shown when `hasBatchNo`.
- `onSelect` sets `row.hasBatchNo`.
- `getPayload` includes `batch_no`.

### Files touched
- `api/item.py`, `api/sales.py`, `api/purchase.py`
- `page/fast_sales_entry/fast_sales_entry.js`, `page/fast_purchase_entry/fast_purchase_entry.js`
- `www/sales_pwa/index.html`
- `hrms/frontend/src/components/FastEntryItems.vue`, `hrms/frontend/src/views/FastSalesEntry.vue`
- `AGENTS.md`

## Latest change: optional "Apply GST" toggle (sales + purchase + quotation)
**Goal:** Allow creating Sales/Purchase invoices without GST when the "Apply GST" checkbox is unchecked. When unchecked, no tax rows are added (neither manual override nor India Compliance auto-template), and totals preview shows 0 tax.

### Server
- `api/sales.py`: `apply_gst = 1 if data.get("apply_gst", 1) else 0`. When 0, skip tax application; after insert, strip any auto-added tax rows (keeping freight actual row). Added `apply_gst` to dedup key.
- `api/purchase.py`: same logic + dedup key update.
- `api/quotation.py`: same logic (no dedup key for quotation).

### Desk pages (sales + purchase + quotation)
- "Apply GST" checkbox added to header row (checked by default).
- `update_totals`: when unchecked, `total_gst_rate = 0`.
- `get_save_data`: includes `apply_gst`.

### PWA (`www/sales_pwa/index.html`)
- "Apply GST" checkbox added; `calcTotals` sets rate=0 when unchecked; `get_save_data` includes `apply_gst`.

### HRMS (`FastSalesEntry.vue`)
- `applyGst` ref (default true); checkbox in invoice section; `effectiveRate` returns 0 when unchecked; payload includes `apply_gst`; reset in `clearForm`.

### Files touched
- `api/sales.py`, `api/purchase.py`
- `page/fast_sales_entry/fast_sales_entry.js`, `page/fast_purchase_entry/fast_purchase_entry.js`
- `www/sales_pwa/index.html`
- `hrms/frontend/src/views/FastSalesEntry.vue`
- `AGENTS.md`

## Open items (from prior logs)
- Purchase-path save dedupe, B2C `NotApplicableError`, `Contact Phone.phone_nos` candidates, zero-stock company rows, PAT revocation, HRMS fork URL.