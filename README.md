# Geeta Corporation — Fast Entry App

ERPNext app (Frappe **v16**) that turns purchase, sales, quotation, payment, stock, ledger and reporting workflows into a fast, keyboard-friendly, single-page experience. Includes custom print formats with e-Invoice / e-Waybill QR support, Party Group management, per-bill TDS/advance payments with carry-forward, bill-level discount modes, WhatsApp sending via a self-hosted gateway, a standalone sales PWA, and a full BI report suite.

Tested against: frappe `v16.31.0`, erpnext `v16.32.0`, india_compliance `v16.8.3`, hrms `v16.19.0`, print_designer `v1.6.5`.

---

## Features

### Fast entry pages (Sidebar → `Fast Entry`)
| Page | Route | Purpose |
|---|---|---|
| Purchase Entry | `/app/fast-purchase-entry` | Add multiple items quickly, auto amount, GST intra/inter, Discount (**Net Total / Grand Total** selector), Freight, WhatsApp/Email with PDF |
| Sales Entry | `/app/fast-sales-entry` | Same fast workflow for Sales Invoices; e-Invoice + e-Waybill aware |
| Quotation Entry | `/app/fast-quotation-entry` | Fast RFQ; warehouse hidden; send via WhatsApp/Email |
| ICT Entry | `/app/fast-ict-entry` | Inter Company Transfer — creates SO→DN→SI and PO→PR→PI from one screen, propagates `fe_pcs`/`fe_box`/`fe_ltr`, posts amounts = PCS × rate after submit |
| Payment Entry | `/app/fast-payment-entry` | Sales/customer payments, single party or whole Party Group in one run (one PE per member, tied in a Party Group Payment) |
| Bulk/Purchase Payment | `/app/fast-bulk-payment` | Supplier payments (PAY mode): **per-invoice TDS + Advance boxes**, advance carry-forward auto-applied oldest-first, TDS books to TDS Payable (net payment) |
| Sales Payment | `/app/fast-sales-payment` | Customer collections: per-invoice TDS + Advance, carry-forward, TDS books to TDS Receivable |
| Stock Report | `/app/fast-stock-report` | Consolidated stock from DN/PR/SI/PI items, per-company breakdown via "All Companies", on-hand Nos/Box/Litre |
| Ledger & P&L | `/app/fast-ledger-pnl` | Party ledger + P&L with live account search |
| Party Groups | `/app/fast-party-group` | Create/manage Party Groups, auto-locks party type, syncs `fe_group` |
| WhatsApp Send | `/app/fast-whatsapp` | Send invoices/quotations on WhatsApp, live gateway status + QR pairing, per-row number add/edit |
| Load Master Data | `/app/fast-master-data` | **Opt-in** master-data bootstrap (System Manager only, dry-run first) |
| Settings | *Fast Entry Settings* DocType | App settings (incl. WhatsApp gateway config) |

### Money rules the app enforces (match ERPNext exactly)
- **Discount**: `Discount On` selector per bill — **Net Total** (discount off the bill net, GST on the discounted net) or **Grand Total** (GST on the full net, discount off the grand total). Every preview surface shows exactly what the saved invoice carries.
- **Purchase TDS is minus**: bank pays invoices + advance − TDS; the TDS posts as a TDS Payable credit (withheld tax owed). Sales TDS mirrors it against TDS Receivable.
- **TDS accounts are mandatory and directional** — `TDS Receivable - <abbr>` on collection, `TDS Payable - <abbr>` on payment. A missing account blocks the payment with the exact account name to create; there is no silent fallback.
- **Freight actually books** (`tax_amount`, not a dead field) and GST rows point at the freight row, so GST covers items + freight in the India-Compliance-approved shape.

### Reports (BI dashboard)
| Page | Route | Features |
|---|---|---|
| Sales Person Performance | `/app/fast-sales-report` | KPI cards, 6 charts, tables, pincode filter, CSV export |
| Sales Person SP Detail | `/app/fast-sp-detail-report` | MTD/QTD/YTD period comparison, KPIs with sparklines, bar charts (Sales, PCS, Top Products), CSV export |
| Area Potential Report | `/app/fast-area-potential-report` | Pincode-based (Area → Pincode → Party), PCS by pincode, Top Products |
| SP Overdue Report | `/app/fast-sp-overdue-report` | Per sales-person outstanding vs sales, age-of-overdue breakdown |
| Party Group Report | `/app/fast-partygroup-report` | Group → customer rollups, Customers by Group, Top Products |

All 4 enhanced reports: **multi-select filters + MTD/QTD/YTD chips + comparison period dropdown + KPI sparklines + frappe-charts bar charts + CSV export**. Auto-load on open and on filter change (debounced 500 ms).

### Send (WhatsApp / Email)
- WhatsApp sends **directly** through a self-hosted OpenWA gateway (`POST …/messages/send-document` with base64 PDF) — no WhatsApp Web juggling. The WhatsApp Send page shows live gateway health, a rotating pairing QR, per-row mobile add/edit with any-format parsing, and surfaces gateway errors inline.
- Email: server sends via SMTP with PDF attached.
- Also enabled on the native **Sales Invoice / Purchase Invoice / Quotation** forms via `erpnext_pi_override.js` (Update Stock pre-tick, Box/Pcs/Ltr columns, send buttons).

### Standalone sales PWA + HRMS mobile view
- `/sales_pwa` — installable, always-draft Fast Sales Entry (works without desk).
- HRMS PWA gets a 6th bottom-nav tab (**Sales Invoice**) rendering a native Fast Sales Entry view with sticky save bar. **Note:** those HRMS changes live in the separate `hrms` app (fork required — see *What stays manual* below), not in this repo.

### Print formats (shipped as fixtures)
- `Custom Sales Invoice` — single-page, Chrome PDF, e-Invoice QR (signed QR), IRN/Ack No/Ack Date, static vehicle details, freight/discount rows, ship-to block.
- `Custom Purchase Invoice`
- `Custom Quotation`
- `Print Invoice 1`
- `Test Print Format`

---

## Installation

```bash
bench init --version version-16 frappe-bench
cd frappe-bench
bench setup requirements
bench new-site dev.localhost
bench get-app https://github.com/MohitPanaliyaDigitalSweep/Geeta-Corporation
bench --site dev.localhost install-app fast_entry_app
```

App order used: `frappe, india_compliance, erpnext, hrms, print_designer, fast_entry_app`.

Also install:

```bash
bench get-app https://github.com/frappe/india_compliance --branch version-16
bench get-app https://github.com/frappe/hrms --branch version-16
bench get-app https://github.com/frappe/print_designer --branch version-16
bench --site dev.localhost install-app india_compliance hrms print_designer
```

After install:

```bash
bench --site dev.localhost migrate
bench --site dev.localhost clear-cache
bench build --app fast_entry_app
```

---

## What install + migrate configure automatically (verified)

`install-app` marks `patches.txt` as done **without running it** (Frappe behavior), so this app does not rely on patches: `after_install` and `after_migrate` both run `install.after_install()`, which converges the schema idempotently on every migrate (safe to re-run; skips doctypes that don't exist yet when ERPNext isn't installed first — `required_apps = ["erpnext"]` auto-installs it).

| Area | Auto-configured |
|---|---|
| 32 Custom Fields (`fe_box`/`fe_pcs`/`fe_ltr`/`fe_total_ltr` × 7 item tables, `fe_group` on Supplier/Customer, `fe_sales_person` + `fe_dedup_key` on Sales Invoice) | ✅ fixtures + setup hook |
| 6 Property Setters (item-name list views, qty → "Accepted Qty", Update Stock pre-ticked on new SI/PI) | ✅ setup hook (never fixtures — would crash installs without ERPNext) |
| 6 desk pages, 5 print formats, 27-item sidebar (sections + icons, exact order), app icon | ✅ fixtures |
| Party Group / Party Group Payment / Fast Entry Settings doctypes + Settings defaults (WhatsApp off, gateway URL, print format, country code) | ✅ |
| GST sandbox | ✅ auto-ON **only** when no Company has a GSTIN yet; real-GSTIN sites are never touched |

---

## What stays manual on each site (handover checklist)

1. **ERPNext Setup Wizard** — company, fiscal year, users (ERPNext's own flow).
2. **Master data** — Items/Customers/UOMs via the opt-in **Load Master Data** page (dry-run first). Never auto-seeded, by design.
3. **Chart of Accounts policy** — `TDS Receivable - <abbr>` / `TDS Payable - <abbr>` (+ Bank). Payments refuse to book TDS until the directional account exists and name it in the error.
4. **WhatsApp gateway** — deploy OpenWA, scan the pairing QR from the WhatsApp Send page, save the API key in Fast Entry Settings (secrets live in site data, never in this repo).
5. **Operator roles** — entry operators need a stock role (Stock User/Manager) or item search returns title-only rows and item pick silently fails.
6. **HRMS mobile tab** — needs a fork of `frappe/hrms` carrying the `frontend/src` changes in this project's history, plus one `yarn build` in `apps/hrms/frontend` after install.
7. **`bench build`** for bundled web assets (standard bench workflow).

---

## Required changes to OTHER apps (nothing is patched — verify instead)

**No source code of frappe / erpnext / india_compliance / hrms / print_designer is modified.** Everything is configured. See [docs/OTHER_APP_CHANGES.md](docs/OTHER_APP_CHANGES.md) for the config checklist, and [docs/SITE_SETUP.md](docs/SITE_SETUP.md) for the exact settings used on the working site.

---

## Project layout

```
fast_entry_app/
├── api/                        # All server-side endpoints
│   ├── sales.py               # Sales entry + autocomplete + taxes + discount modes
│   ├── purchase.py            # Purchase entry
│   ├── quotation.py           # Quotation entry
│   ├── ict.py                 # Inter Company Transfer (in inter_company_transfer.py)
│   ├── payment.py             # Payment engine: per-bill TDS/advance, carry-forward, group runs
│   ├── party.py               # Customer/Supplier details, GST handling
│   ├── party_group.py         # Party Group CRUD + fe_group sync
│   ├── stock_report.py        # Stock incl. Stock Balance pack-UOM augmentation
│   ├── item.py                # Item/UOM lookups, invoice-UOM guard
│   ├── ledger_pnl.py          # Ledger + P&L
│   ├── invoice_send.py        # WhatsApp (OpenWA) + Email sending
│   ├── openwa.py / wa_session.py / wa_health.py  # Gateway client, pairing, health checks
│   ├── reports.py             # 4 report APIs
│   └── sales_person_report.py # Original SP performance API
├── fast_entry_app/
│   ├── doctype/               # Fast Entry Settings, ICT (+docs), Party Group (+PGroup Payment)
│   ├── page/                  # All fast_* pages (json/py/js/css)
│   └── www/sales_pwa/         # Standalone sales PWA (index.html/py, sw.js)
├── fixtures/                  # custom_field.json (32), workspace_sidebar.json (27), print_format.json (5)
├── maintenance/               # stock_uom_to_pieces.py (pieces migration, dry-run by default)
├── master_data/bundles/       # Reference + anonymised seed bundles for the loader page
├── public/js/erpnext_pi_override.js  # Update-Stock default + Box/Pcs/Ltr + send buttons on native SI/PI/Quotation
├── public/css/…               # Globally-loaded CSS mirrors of page CSS (keep identical; bump ?v= in hooks.py)
├── setup_custom_fields.py     # Idempotent custom-field + property-setter sync (runs on install + migrate)
├── install.py                 # after_install: schema sync + GST sandbox guard
└── workspace_sidebar/fast_entry.json
```

---

## Getting support

- ERPNext: https://docs.erpnext.com
- Frappe v16: https://frappeframework.com/docs
- India Compliance: https://github.com/resilient-tech/india-compliance
