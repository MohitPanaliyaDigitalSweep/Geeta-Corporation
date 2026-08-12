import frappe

def execute():
    fields = [
        {
            "dt": "Purchase Invoice Item",
            "fieldname": "fe_box",
            "fieldtype": "Float",
            "label": "Box",
            "insert_after": "item_name",
            "module": "Fast Entry App",
            "default": 0,
        },
        {
            "dt": "Purchase Invoice Item",
            "fieldname": "fe_pcs",
            "fieldtype": "Float",
            "label": "PCS",
            "insert_after": "fe_box",
            "module": "Fast Entry App",
            "read_only": 1,
            "default": 0,
        },
        {
            "dt": "Purchase Invoice Item",
            "fieldname": "fe_ltr",
            "fieldtype": "Float",
            "label": "LTR",
            "insert_after": "fe_pcs",
            "module": "Fast Entry App",
            "read_only": 1,
            "default": 0,
        },
        {
            "dt": "Sales Invoice Item",
            "fieldname": "fe_box",
            "fieldtype": "Float",
            "label": "Box",
            "insert_after": "item_name",
            "module": "Fast Entry App",
            "default": 0,
        },
        {
            "dt": "Sales Invoice Item",
            "fieldname": "fe_pcs",
            "fieldtype": "Float",
            "label": "PCS",
            "insert_after": "fe_box",
            "module": "Fast Entry App",
            "read_only": 1,
            "default": 0,
        },
        {
            "dt": "Sales Invoice Item",
            "fieldname": "fe_ltr",
            "fieldtype": "Float",
            "label": "LTR",
            "insert_after": "fe_pcs",
            "module": "Fast Entry App",
            "read_only": 1,
            "default": 0,
        },
    ]

    for f in fields:
        existing = frappe.db.exists("Custom Field", {"dt": f["dt"], "fieldname": f["fieldname"]})
        if not existing:
            cf = frappe.new_doc("Custom Field")
            cf.update(f)
            cf.insert(ignore_permissions=True)
            print(f"Created: {f['dt']} - {f['fieldname']}")
        else:
            print(f"Exists: {f['dt']} - {f['fieldname']}")
    frappe.db.commit()
