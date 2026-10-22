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

## Open items (from prior logs)
- Purchase-path save dedupe, B2C `NotApplicableError`, `Contact Phone.phone_nos` candidates, zero-stock company rows, PAT revocation, HRMS fork URL.