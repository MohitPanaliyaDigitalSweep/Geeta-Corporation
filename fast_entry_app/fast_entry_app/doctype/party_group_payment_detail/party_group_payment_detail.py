import frappe
from frappe.model.document import Document


class PartyGroupPaymentDetail(Document):
    # Table rows are written by create_party_group_payment in api/payment.py;
    # all validation for the whole run lives on the parent, so nothing is needed
    # here. The class must exist or get_controller() cannot import the doctype.
    pass
