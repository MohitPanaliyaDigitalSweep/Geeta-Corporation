import frappe


def execute():
    """Migrate existing fe_group text values to Party Group DocType records."""

    # Migrate Supplier fe_group values
    suppliers = frappe.get_all(
        "Supplier",
        filters={"fe_group": ["is", "set"], "fe_group": ["!=", ""]},
        fields=["name", "fe_group"],
    )

    for sup in suppliers:
        group_name = sup.fe_group.strip()
        if not group_name:
            continue

        _ensure_party_group(group_name, "Supplier", sup.name, "Supplier")

    # Migrate Customer fe_group values
    customers = frappe.get_all(
        "Customer",
        filters={"fe_group": ["is", "set"], "fe_group": ["!=", ""]},
        fields=["name", "fe_group"],
    )

    for cust in customers:
        group_name = cust.fe_group.strip()
        if not group_name:
            continue

        _ensure_party_group(group_name, "Customer", cust.name, "Customer")

    frappe.db.commit()


def _ensure_party_group(group_name, group_type, party_name, party_type):
    """Create Party Group if not exists, add party if not already in it."""

    # Determine group type: if we have both suppliers and customers, use "Both"
    existing = frappe.db.get_value("Party Group", {"group_name": group_name}, "name")

    if existing:
        doc = frappe.get_doc("Party Group", existing)
    else:
        doc = frappe.get_doc({
            "doctype": "Party Group",
            "group_name": group_name,
            "group_type": group_type,
            "description": f"Auto-migrated from fe_group field",
        })

    # Check if party already in group
    already_exists = False
    for row in doc.parties:
        if row.party_type == party_type and row.party == party_name:
            already_exists = True
            break

    if not already_exists:
        party_doc = frappe.get_doc(party_type, party_name)
        doc.append("parties", {
            "party_type": party_type,
            "party": party_name,
            "party_name": party_doc.name,
            "gstin": getattr(party_doc, "gstin", None) or "",
        })

    if not existing:
        doc.insert(ignore_permissions=True)
    else:
        doc.save(ignore_permissions=True)

    # Update fe_group to link to the Party Group
    frappe.db.set_value(party_type, party_name, "fe_group", doc.name, update_modified=False)
