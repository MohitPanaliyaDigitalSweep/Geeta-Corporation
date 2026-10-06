# Copyright (c) 2026, Fast Entry App and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class PartyGroupPayment(Document):
    """Group-level record of one payment run across a Party Group.

    Why this exists: a Party Group spans several parties (e.g. every "IOCL - <x>"
    supplier), and an ERPNext Payment Entry can only carry ONE party. So a group
    payment necessarily produces several Payment Entries, and afterwards there is
    nothing in ERP that says "these PEs were one decision, taken against this
    group, for this much". This doctype is that missing record -- the same reason
    Inter Company Transfer persists its own header instead of leaving the
    generated Sales/Purchase Invoices to speak for themselves.

    One row per member party, each linking the Payment Entry that was created
    for it, so the invoices behind a row are reachable via that PE's references.
    """

    def validate(self):
        self.set_payment_type()
        self.set_group_name()
        self.validate_payments()

    def set_payment_type(self):
        if not self.party_type:
            frappe.throw(_("Party Type is required"))
        self.payment_type = "Receive" if self.party_type == "Customer" else "Pay"

    def set_group_name(self):
        if not self.group:
            return
        if not frappe.db.exists("Party Group", self.group):
            frappe.throw(_("Party Group {0} does not exist").format(self.group))
        self.group_name = self.group

    def validate_payments(self):
        if not self.payments:
            frappe.throw(_("Add at least one member payment"))

        seen = {}
        total = 0.0
        for row in self.payments:
            if not row.party:
                frappe.throw(_("Row {0}: party is required").format(row.idx))
            if row.party_type != self.party_type:
                frappe.throw(
                    _("Row {0}: party type {1} does not match this document's {2}").format(
                        row.idx, row.party_type, self.party_type
                    )
                )
            if row.party in seen:
                frappe.throw(
                    _("Row {0}: {1} is listed more than once - a group member can only be paid once per document").format(
                        row.idx, row.party
                    )
                )
            seen[row.party] = True

            if flt(row.paid_amount) <= 0:
                frappe.throw(_("Row {0}: paid amount must be greater than 0").format(row.idx))

            row.party_name = row.party_name or _party_display_name(self.party_type, row.party)
            total += flt(row.paid_amount)

        # A party that is not actually in the group would silently corrupt the
        # group's meaning, so refuse it rather than quietly widening the group.
        if self.group:
            members = set(_group_member_names(self.group, self.party_type))
            if members:
                outside = [r.party for r in self.payments if r.party not in members]
                if outside:
                    frappe.throw(
                        _("These parties are not members of group {0}: {1}").format(
                            self.group, ", ".join(outside)
                        )
                    )

        self.total_amount = total
        self.member_count = len(self.payments)

    def on_submit(self):
        self.db_set("member_count", len(self.payments))

    @property
    def party_groups_of_member(self):
        return self.group


def _party_display_name(party_type, party):
    if party_type == "Customer":
        return frappe.db.get_value("Customer", party, "customer_name") or party
    return frappe.db.get_value("Supplier", party, "supplier_name") or party


def _group_member_names(group, party_type):
    return frappe.get_all(
        "Party Group Party",
        filters={"parent": group, "party_type": party_type},
        pluck="party",
    )