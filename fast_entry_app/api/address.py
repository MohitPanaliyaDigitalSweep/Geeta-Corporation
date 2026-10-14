"""Default address resolution for Fast Entry documents.

The Desk forms populate the party / company address fields from the linked
Address records (client-side "primary address" pickers). Documents created
through the API had no such defaults, so fields like
``Sales Invoice.customer_address`` (mandatory for e-Invoice) stayed blank.

This module mirrors that Desk behaviour server-side. It is best-effort: a
missing Address is never fatal here, the downstream India Compliance /
ERPNext validation still owns the "this is required" decision.
"""

import frappe
from frappe.contacts.doctype.address.address import get_default_address

# doctype -> (party_doctype, party_field, party_billing_field)
PARTY_ADDRESS_FIELDS = {
    "Sales Invoice": ("Customer", "customer", "customer_address"),
    "Quotation": ("Customer", "party_name", "customer_address"),
    "Purchase Invoice": ("Supplier", "supplier", "supplier_address"),
}

# doctype -> the company's own (bill_from for sales / bill_to for purchase) field
COMPANY_ADDRESS_FIELDS = {
    "Sales Invoice": "company_address",
    "Quotation": "company_address",
    "Purchase Invoice": "billing_address",
}

# Selling documents also carry the buyer's ship-to address
SHIPPING_ADDRESS_FIELDS = {
    "Sales Invoice": "shipping_address_name",
    "Quotation": "shipping_address_name",
}


def set_default_addresses(doc):
    """Fill party / company / shipping address fields from default Addresses.

    Safe to call at any point before ``doc.insert()``. Never raises: failures
    are logged so address resolution can't block invoice creation.
    """
    try:
        _set_party_address(doc)
        _set_company_address(doc)
    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            "Fast Entry: default address resolution failed for {0}".format(doc.doctype),
        )


def _set_party_address(doc):
    spec = PARTY_ADDRESS_FIELDS.get(doc.doctype)
    if not spec:
        return

    party_doctype, party_field, billing_field = spec
    party = doc.get(party_field)
    if not party:
        return

    if not doc.get(billing_field):
        billing = get_default_address(party_doctype, party)
        if billing:
            doc.set(billing_field, billing)

    shipping_field = SHIPPING_ADDRESS_FIELDS.get(doc.doctype)
    if shipping_field and not doc.get(shipping_field):
        shipping = get_default_address(party_doctype, party, "is_shipping_address")
        if shipping and shipping != doc.get(billing_field):
            doc.set(shipping_field, shipping)


def _set_company_address(doc):
    field = COMPANY_ADDRESS_FIELDS.get(doc.doctype)
    if not field or doc.get(field) or not doc.get("company"):
        return

    address = get_default_address("Company", doc.company)
    if address:
        doc.set(field, address)
