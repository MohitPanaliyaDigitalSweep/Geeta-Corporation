app_name = "fast_entry_app"
app_title = "Fast Entry App"
app_publisher = "developers@fastentry.local"
app_description = "Fast Purchase and Sales Entry for ERPNext"
app_email = "developers@fastentry.local"
app_license = "gpl-3.0"

# Apps
add_to_apps_screen = [
    {
        "name": "fast_entry_app",
        "title": "Fast Entry",
        "route": "/app/fast-purchase-entry",
        "logo": "/assets/fast_entry_app/icons/desktop_icons/solid/fast_entry.svg",
    }
]

# Includes in <head>
app_include_css = [
    "/assets/fast_entry_app/css/fast_entry_app.css",
    "/assets/fast_entry_app/css/fast_purchase_entry.css",
    "/assets/fast_entry_app/css/fast_sales_entry.css",
    "/assets/fast_entry_app/css/fast_ict_entry.css",
    "/assets/fast_entry_app/css/fast_quotation_entry.css",
    "/assets/fast_entry_app/css/fast_party_group.css",
    "/assets/fast_entry_app/css/fast_ledger_pnl.css",
    "/assets/fast_entry_app/css/fast_stock_report.css",
    "/assets/fast_entry_app/css/fast_payment_entry.css",
    "/assets/fast_entry_app/css/fast_bulk_payment.css",
    "/assets/fast_entry_app/css/fast_sales_payment.css",
    "/assets/fast_entry_app/css/report_ui_components.css",
]
app_include_js = [
    "/assets/fast_entry_app/js/fast_entry_app.js",
    "/assets/fast_entry_app/js/report_ui_components.js",
]

# Only load PI/SI override on those forms
doctype_js = {
    "Purchase Invoice": "public/js/erpnext_pi_override.js",
    "Sales Invoice": "public/js/erpnext_pi_override.js",
    "Quotation": "public/js/erpnext_pi_override.js",
}



# Fixtures
fixtures = [
    {
        "dt": "Custom Field",
        "filters": [["module", "=", "Fast Entry App"]],
    },
    {
        "dt": "Workspace Sidebar",
        "filters": [["name", "=", "Fast Entry"]],
    },
    {
        "dt": "Print Format",
        "filters": [
            [
                "name",
                "in",
                [
                    "Print Invoice 1",
                    "Custom Sales Invoice",
                    "Custom Purchase Invoice",
                    "Custom Quotation",
                ],
            ]
        ],
    },
]
