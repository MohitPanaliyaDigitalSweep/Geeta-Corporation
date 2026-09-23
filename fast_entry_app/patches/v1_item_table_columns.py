import frappe

from fast_entry_app.setup_custom_fields import execute as setup_custom_fields


def execute():
    setup_custom_fields()
    frappe.db.commit()
