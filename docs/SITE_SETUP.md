# SITE_SETUP — Exact configuration of the working Geeta Corporation bench

This is the step-by-step record of how the site **dev.localhost** was configured so a fresh install can be reproduced. Run the commands from your bench root unless noted.

## Environment

| Item | Value |
|---|---|
| Bench | `/home/giris/bench` |
| Site | `dev.localhost` |
| Web | `127.0.0.1:8000` (gunicorn, 25 workers) |
| Supervisord/systemd | `frappe-bench.service` |
| Server control | `sudo systemctl stop/start frappe-bench.service` |
| Login | `Administrator / admin` |

## 1. Apps

```bash
bench get-app --branch version-16 https://github.com/frappe/frappe
bench get-app --branch version-16 https://github.com/resilient-tech/india-compliance
bench get-app --branch version-16 https://github.com/frappe/erpnext
bench get-app --branch version-16 https://github.com/frappe/hrms
bench get-app --branch version-16 https://github.com/frappe/print_designer
bench get-app <this repo>
```

`sites/apps.txt` (order matters):

```
frappe
india_compliance
erpnext
hrms
print_designer
fast_entry_app
```

## 2. Install + migrate

```bash
bench setup requirements
bench new-site dev.localhost
bench --site dev.localhost install-app india_compliance erpnext hrms print_designer fast_entry_app
bench --site dev.localhost set-admin-password admin
bench --site dev.localhost migrate
```

`migrate` runs the two app patches and syncs all fixtures (custom fields, sidebar, print formats).

## 3. Bench-level config

`sites/common_site_config.json` (extract of the working defaults):

```json
{
  "background_workers": 1,
  "db_host": "127.0.0.1",
  "db_port": 3307,
  "default_site": "dev.localhost",
  "file_watcher_port": 6787,
  "frappe_user": "giris",
  "gunicorn_workers": 25,
  "live_reload": true,
  "rebase_on_pull": false,
  "redis_queue": "redis://127.0.0.1:6379",
  "restart_supervisor_on_update": false,
  "restart_systemd_on_update": false,
  "serve_default_site": true,
  "webserver_port": 8000
}
```

`dev.localhost/site_config.json` highlights:

```json
{
  "developer_mode": 1
}
```

(DB name/user/password are auto-generated UUID values on this machine — recreate via bench.)

## 4. Frontend build

PSA: run from each build dir when HRMS ships separate bundles:

```bash
cd apps/hrms/frontend && yarn install && yarn build
cd apps/hrms/roster   && yarn install && yarn build
cd /home/giris/bench && bench build --app fast_entry_app
bench --site dev.localhost clear-cache
```

## 5. Desk configuration (once per install)

Each of these is a desk action because the value lives in the database:

1. **GST Settings** — enable e-Invoice, e-Way Bill, Sandbox; `api_secret = test_sandbox_api_key` (see OTHER_APP_CHANGES §7).
2. **Email Account** `Brevo SMTP` as default outgoing (OTHER_APP_CHANGES §8).
3. **UOM `Box`** → `must_be_whole_number = 0`.
4. **Item `2900145`** UOM factors Nos=200 / Litre=0.06 / Box=1.0 (data, not app logic).
5. Confirm **Workspace Sidebar `Fast Entry`** shows 19 items (OTHER_APP_CHANGES §5); re-run `migrate` if a downstream app install overwrote it.
6. Optionally run demo data: `scripts/generate_test_data.py`.

## 6. e-Invoice sandbox test (optional verification)

```bash
bench --site dev.localhost console
```

```python
from india_compliance.gst_india.utils.e_invoice import generate_e_invoice
generate_e_invoice("SINV-26-00191")
```

On success the Sales Invoice gets `einvoice_status = Generated` + an `irn`. (One known quirk: `frappe.enqueue` inside `log_e_invoice` needs the RQ worker/`bench worker` running for the `E Invoice Log` row to appear; the IRN/status on the SI updates regardless.)

## 7. Licensing

App: GPL-3.0 (see `license.txt`). ERPNext/HRMS GPL-3.0, Frappe MIT, india_compliance + print_designer GPL-3.0.

---

## Reproducing the report pages

The 15 pages (`fast_purchase_entry`, `fast_sales_entry`, `fast_quotation_entry`, `fast_ict_entry`, `fast_payment_entry`, `fast_bulk_payment`, `fast_sales_payment`, `fast_stock_report`, `fast_ledger_pnl`, `fast_party_group`, `fast_sales_report`, `fast_sp_detail_report`, `fast_area_potential_report`, `fast_sp_overdue_report`, `fast_partygroup_report`) live in `fast_entry_app/fast_entry_app/page/*` and register on install. No manual `tabPage` inserts needed.