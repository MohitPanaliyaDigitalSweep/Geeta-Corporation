import frappe
from frappe.model.document import Document


class PartyGroup(Document):
    def validate(self):
        self.validate_parties()

    def validate_parties(self):
        seen = set()
        for row in self.parties:
            key = (row.party_type, row.party)
            if key in seen:
                frappe.throw(f"Duplicate party: {row.party_type} {row.party}")
            seen.add(key)

            # Auto-fill party_name and gstin
            if row.party_type == "Supplier":
                doc = frappe.get_doc("Supplier", row.party)
                row.party_name = doc.supplier_name
                row.gstin = doc.gstin
            elif row.party_type == "Customer":
                doc = frappe.get_doc("Customer", row.party)
                row.party_name = doc.customer_name
                row.gstin = doc.gstin
