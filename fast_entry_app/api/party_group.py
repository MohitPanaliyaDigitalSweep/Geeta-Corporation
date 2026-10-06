import json

import frappe
from frappe import _
from frappe.utils import flt


def resolve_group(party_type, party):
    """The Party Group a party belongs to, or "" when it is ungrouped.

    Single source of truth for group membership, because there are two places
    it can be recorded and callers were checking only one of them:

      1. the Customer/Supplier.fe_group Link (fast to read, set by this app)
      2. a Party Group Party child row (the authority)

    Callers that only read fe_group silently drop parties grouped via the child
    table, so they show no group in the UI and no expansion in a payment run.
    """
    if not party:
        return ""
    group = ""
    if frappe.db.has_column(party_type, "fe_group"):
        group = frappe.db.get_value(party_type, party, "fe_group") or ""
    if not group:
        group = frappe.db.get_value("Party Group Party", {"party_type": party_type, "party": party}, "parent") or ""
    return group


@frappe.whitelist()
def get_party_groups(group_type=None):
    """List all Party Groups, optionally filtered by type."""
    filters = {}
    if group_type:
        filters["group_type"] = group_type

    groups = frappe.get_all(
        "Party Group",
        filters=filters,
        fields=["name", "group_name", "group_type", "description"],
        order_by="group_name asc",
    )

    for g in groups:
        g["party_count"] = frappe.db.count("Party Group Party", {"parent": g.name})

    return groups


@frappe.whitelist()
def create_party_group(data):
    """Create or update a Party Group with parties."""
    if isinstance(data, str):
        data = json.loads(data)

    group_name = data.get("group_name", "").strip()
    if not group_name:
        frappe.throw(_("Group Name is required"))

    # Use explicit existing_name if provided, otherwise lookup by group_name
    existing = data.get("existing_name") or frappe.db.get_value("Party Group", {"group_name": group_name}, "name")

    if existing:
        doc = frappe.get_doc("Party Group", existing)
        # Clear fe_group on old parties before removing them
        for old_row in doc.parties:
            if old_row.party and frappe.db.exists(old_row.party_type, old_row.party):
                frappe.db.set_value(old_row.party_type, old_row.party, "fe_group", None, update_modified=False)
        doc.group_type = data.get("group_type", doc.group_type)
        doc.description = data.get("description", doc.description)
        doc.parties = []
    else:
        doc = frappe.get_doc({
            "doctype": "Party Group",
            "group_name": group_name,
            "group_type": data.get("group_type", "Supplier"),
            "description": data.get("description", ""),
        })

    for p in data.get("parties", []):
        party_type = p.get("party_type")
        party = p.get("party")
        if not party_type or not party:
            continue

        # Auto-fill party_name and gstin
        party_doc = frappe.get_doc(party_type, party)
        doc.append("parties", {
            "party_type": party_type,
            "party": party,
            "party_name": party_doc.name,
            "gstin": getattr(party_doc, "gstin", None) or "",
        })

    if existing:
        doc.save(ignore_permissions=True)
    else:
        doc.insert(ignore_permissions=True)

    # Set fe_group on all parties in this group
    for row in doc.parties:
        if row.party and frappe.db.exists(row.party_type, row.party):
            frappe.db.set_value(row.party_type, row.party, "fe_group", doc.name, update_modified=False)

    frappe.db.commit()
    return {"name": doc.name, "group_name": doc.group_name}


@frappe.whitelist()
def delete_party_group(name):
    """Delete a Party Group and unlink all parties."""
    if not frappe.db.exists("Party Group", name):
        frappe.throw(_("Party Group {0} not found").format(name))

    # Clear fe_group on all linked suppliers/customers
    suppliers = frappe.get_all("Party Group Party",
                               filters={"parent": name, "party_type": "Supplier"},
                               fields=["party"])
    for s in suppliers:
        frappe.db.set_value("Supplier", s.party, "fe_group", None, update_modified=False)

    customers = frappe.get_all("Party Group Party",
                               filters={"parent": name, "party_type": "Customer"},
                               fields=["party"])
    for c in customers:
        frappe.db.set_value("Customer", c.party, "fe_group", None, update_modified=False)

    frappe.delete_doc("Party Group", name, ignore_permissions=True)
    frappe.db.commit()
    return {"ok": True}


@frappe.whitelist()
def get_group_parties(group_name):
    """Get all parties in a group."""
    if not frappe.db.exists("Party Group", group_name):
        frappe.throw(_("Party Group {0} not found").format(group_name))

    parties = frappe.get_all(
        "Party Group Party",
        filters={"parent": group_name},
        fields=["party_type", "party", "party_name", "gstin"],
    )
    return parties


def _default_mode_of_payment(company):
    mop = frappe.db.get_value("Mode of Payment", {"type": "Bank", "enabled": 1}, "name")
    if mop:
        return mop
    mop = frappe.db.get_value("Mode of Payment", {"enabled": 1}, "name")
    if mop:
        return mop
    return "Wire Transfer"


def _first_bank_account(company):
    acc = frappe.db.get_value("Account", {"company": company, "account_type": "Bank", "is_group": 0}, "name")
    if acc:
        return acc
    return frappe.db.get_value("Account", {"company": company, "account_type": "Bank"}, "name")


def _first_account(company, account_type):
    return frappe.db.get_value(
        "Account",
        {"company": company, "account_type": account_type, "is_group": 0},
        "name",
    )
