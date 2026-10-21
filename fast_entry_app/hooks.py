app_name = "fast_entry_app"
app_title = "Geeta Corporation"
app_publisher = "developers@fastentry.local"
app_description = "Fast Purchase and Sales Entry for ERPNext"
app_email = "developers@fastentry.local"
app_license = "gpl-3.0"

# ERPNext is a hard dependency: Inter Company Transfer imports
# erpnext.controllers.stock_controller, and every custom field we ship targets
# an ERPNext doctype. In Frappe v16 this hook also auto-installs ERPNext before
# this app's fixtures/patches run, and blocks uninstalling it while we are here.
required_apps = ["erpnext"]

# Apps
add_to_apps_screen = [
    {
        "name": "fast_entry_app",
        "title": "Geeta Corporation",
        "route": "/app/fast-purchase-entry",
        "logo": "/assets/fast_entry_app/icons/desktop_icons/solid/fast_entry.svg",
    }
]

# Includes in <head>
# NOTE: `?v=` suffix forces browsers to refetch after fixes. Frappe serves
# /assets with `Cache-Control: max-age=43200` (12h) and does NOT version plain
# public files (only *.bundle.* get hashed names), so without this suffix users
# keep running stale JS/CSS for half a day. Bump the suffix on every release
# that touches public/css or public/js.
_FE_ASSET_V = "20261021c"
app_include_css = [
    f"/assets/fast_entry_app/css/fast_entry_app.css?v={_FE_ASSET_V}",
    f"/assets/fast_entry_app/css/fast_purchase_entry.css?v={_FE_ASSET_V}",
    f"/assets/fast_entry_app/css/fast_sales_entry.css?v={_FE_ASSET_V}",
    f"/assets/fast_entry_app/css/fast_ict_entry.css?v={_FE_ASSET_V}",
    f"/assets/fast_entry_app/css/fast_quotation_entry.css?v={_FE_ASSET_V}",
    f"/assets/fast_entry_app/css/fast_party_group.css?v={_FE_ASSET_V}",
    f"/assets/fast_entry_app/css/fast_ledger_pnl.css?v={_FE_ASSET_V}",
    f"/assets/fast_entry_app/css/fast_stock_report.css?v={_FE_ASSET_V}",
    f"/assets/fast_entry_app/css/fast_payment_entry.css?v={_FE_ASSET_V}",
    f"/assets/fast_entry_app/css/fast_bulk_payment.css?v={_FE_ASSET_V}",
    f"/assets/fast_entry_app/css/fast_sales_payment.css?v={_FE_ASSET_V}",
    f"/assets/fast_entry_app/css/report_ui_components.css?v={_FE_ASSET_V}",
]
app_include_js = [
    f"/assets/fast_entry_app/js/fast_entry_app.js?v={_FE_ASSET_V}",
    f"/assets/fast_entry_app/js/report_ui_components.js?v={_FE_ASSET_V}",
]

# Only load PI/SI override on those forms
doctype_js = {
    "Purchase Invoice": "public/js/erpnext_pi_override.js",
    "Sales Invoice": "public/js/erpnext_pi_override.js",
    "Quotation": "public/js/erpnext_pi_override.js",
    "Sales Order": "public/js/erpnext_pi_override.js",
    "Purchase Order": "public/js/erpnext_pi_override.js",
    "Delivery Note": "public/js/erpnext_pi_override.js",
    "Purchase Receipt": "public/js/erpnext_pi_override.js",
    "Stock Entry": "public/js/erpnext_pi_override.js",
    "Asset Capitalization": "public/js/erpnext_pi_override.js",
    "Asset Movement": "public/js/erpnext_pi_override.js",
    "BOM": "public/js/erpnext_pi_override.js",
    "BOM Creator": "public/js/erpnext_pi_override.js",
    "Bill of Entry": "public/js/erpnext_pi_override.js",
    "Blanket Order": "public/js/erpnext_pi_override.js",
    "Installation Note": "public/js/erpnext_pi_override.js",
    "Landed Cost Voucher": "public/js/erpnext_pi_override.js",
    "Material Request": "public/js/erpnext_pi_override.js",
    "Opportunity": "public/js/erpnext_pi_override.js",
    "POS Invoice": "public/js/erpnext_pi_override.js",
    "Packing Slip": "public/js/erpnext_pi_override.js",
    "Pick List": "public/js/erpnext_pi_override.js",
    "Product Bundle": "public/js/erpnext_pi_override.js",
    "Request for Quotation": "public/js/erpnext_pi_override.js",
    "Stock Reconciliation": "public/js/erpnext_pi_override.js",
    "Subcontracting Inward Order": "public/js/erpnext_pi_override.js",
    "Subcontracting Order": "public/js/erpnext_pi_override.js",
    "Subcontracting Receipt": "public/js/erpnext_pi_override.js",
    "Supplier Quotation": "public/js/erpnext_pi_override.js",
    "Work Order": "public/js/erpnext_pi_override.js",
}

# Splice the Fast Entry Box / Pcs / Ltr pack-UOM columns into the standard
# "Stock Balance" query report. The report view calls this whitelisted entry
# point; the override runs the original unchanged and augments its result
# (fast_entry_app.api.stock_report.override_query_report_run).
override_whitelisted_methods = {
    "frappe.desk.query_report.run": "fast_entry_app.api.stock_report.override_query_report_run",
}



# Doctype controller subclasses. Converge ERPNext's "Grand Total" discount mode
# onto its "Net Total" bookkeeping: stock distributes a Grand Total discount over
# a tax-inclusive base (grand_total - actual taxes), which distorts net_total and
# collapses every total to zero when the discount reaches that base. The override
# engine (fast_entry_app.overrides.taxes_and_totals) runs the whole calculation
# as "Net Total" when a Grand Total discount is present, then restores the doc
# field, plus it rejects discount >= net_total so net/grand are never zero.
# frappe resolves the LAST entry per doctype; india_compliance only overrides
# "Customize Form", so there is no conflict.
override_doctype_class = {
    "Sales Invoice": "fast_entry_app.overrides.controllers.SalesInvoice",
    "Purchase Invoice": "fast_entry_app.overrides.controllers.PurchaseInvoice",
    "Quotation": "fast_entry_app.overrides.controllers.Quotation",
}


# Fixtures
fixtures = [
    {
        "dt": "Custom Field",
        "filters": [["module", "=", "Fast Entry App"]],
    },
    {
        "dt": "Workspace Sidebar",
        "filters": [["name", "=", "Geeta Corporation"]],
    },
    {
        "dt": "Print Format",
        "filters": [
            [
                "name",
                "in",
                [
                    "Custom Sales Invoice",
                    "Custom Purchase Invoice",
                    "Custom Quotation",
                ],
            ]
        ],
    },
    {
        "dt": "List View Settings",
        "filters": [["name", "=", "Inter Company Transfer"]],
    },
]

# Patches are marked completed (not executed) by `install-app`, and a site that
# installed us before ERPNext will never run the v2 patch either, because it was
# already recorded as done. These two hooks make the schema converge instead:
# once at install time, then on every migrate.
after_install = "fast_entry_app.install.after_install"
after_migrate = "fast_entry_app.install.after_install"
