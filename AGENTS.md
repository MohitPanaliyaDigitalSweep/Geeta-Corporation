# Fast Entry App — AGENTS.md

## Scope
Fast Entry desk pages + ERPNext form overrides for Sales/Purchase Invoice / Quotation.
App module: `fast_entry_app`. Lives at `apps/fast_entry_app/`.

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

## Latest change: optional "Apply GST" toggle (sales + purchase)
**Goal:** Allow creating Sales/Purchase invoices without GST when the "Apply GST" checkbox is unchecked. When unchecked, no tax rows are added (neither manual override nor India Compliance auto-template), and totals preview shows 0 tax.

### Server
- `api/sales.py`: `apply_gst = 1 if data.get("apply_gst", 1) else 0`. When 0, skip tax application; after insert, strip any auto-added tax rows (keeping freight actual row). Added `apply_gst` to dedup key.
- `api/purchase.py`: same logic + dedup key update.

### Desk pages (sales + purchase)
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