import frappe


def execute():
    fields = []
    doc_types = [
        "Purchase Invoice Item",
        "Sales Invoice Item",
        "Quotation Item",
        "Sales Order Item",
        "Purchase Order Item",
        "Delivery Note Item",
        "Purchase Receipt Item",
    ]

    for dt in doc_types:
        fields.extend([
            {
                "dt": dt,
                "fieldname": "fe_box",
                "fieldtype": "Float",
                "label": "Box",
                "insert_after": "qty",
                "in_list_view": 1,
                "module": "Fast Entry App",
                "default": 0,
            },
            {
                "dt": dt,
                "fieldname": "fe_pcs",
                "fieldtype": "Float",
                "label": "PCS",
                "insert_after": "fe_box",
                "in_list_view": 1,
                "module": "Fast Entry App",
                "read_only": 1,
                "default": 0,
            },
            {
                "dt": dt,
                "fieldname": "fe_ltr",
                "fieldtype": "Float",
                "label": "LTR",
                "insert_after": "fe_pcs",
                "in_list_view": 1,
                "module": "Fast Entry App",
                "read_only": 1,
                "default": 0,
            },
            {
                "dt": dt,
                "fieldname": "fe_total_ltr",
                "fieldtype": "Float",
                "label": "Total LTR",
                "insert_after": "fe_ltr",
                "in_list_view": 1,
                "module": "Fast Entry App",
                "read_only": 1,
                "default": 0,
            },
        ])

    for f in fields:
        existing = frappe.db.exists("Custom Field", {"dt": f["dt"], "fieldname": f["fieldname"]})
        if not existing:
            cf = frappe.new_doc("Custom Field")
            cf.update(f)
            cf.insert(ignore_permissions=True)
            print(f"Created: {f['dt']} - {f['fieldname']}")
        else:
            cf = frappe.get_doc("Custom Field", existing)
            cf.flags.ignore_validate = True
            for key in ("label", "insert_after", "in_list_view", "read_only", "default", "module"):
                if key in f:
                    cf.set(key, f[key])
            cf.save(ignore_permissions=True)
            print(f"Updated: {f['dt']} - {f['fieldname']}")

    _apply_property_setters()
    frappe.db.commit()


def _apply_property_setters():
    """Item table columns: Item | Item Name | Accepted Qty | Box | PCS | LTR | Total LTR | Rate | Amount."""
    setters = [
        ("Purchase Invoice Item", "item_name", "in_list_view", "1", "Int"),
        ("Sales Invoice Item", "item_name", "in_list_view", "1", "Int"),
        ("Sales Invoice Item", "warehouse", "in_list_view", "0", "Int"),
        ("Sales Invoice Item", "qty", "label", "Accepted Qty", "Data"),
    ]

    for doc_type, field_name, property, value, property_type in setters:
        exists = frappe.db.exists(
            "Property Setter",
            {
                "doc_type": doc_type,
                "field_name": field_name,
                "property": property,
            },
        )
        if not exists:
            frappe.get_doc(
                {
                    "doctype": "Property Setter",
                    "doc_type": doc_type,
                    "field_name": field_name,
                    "property": property,
                    "property_type": property_type,
                    "value": value,
                }
            ).insert(ignore_permissions=True)
            print(f"Property Setter created: {doc_type} {field_name} {property}={value}")
        else:
            ps = frappe.get_doc("Property Setter", exists)
            if str(ps.value) != str(value):
                ps.value = value
                ps.save(ignore_permissions=True)
                print(f"Property Setter updated: {doc_type} {field_name} {property}={value}")
