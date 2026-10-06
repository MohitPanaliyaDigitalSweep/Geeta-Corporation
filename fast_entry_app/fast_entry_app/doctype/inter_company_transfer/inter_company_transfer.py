import frappe
from frappe import _
from frappe.utils import flt

from erpnext.controllers.stock_controller import StockController

INTER_COMPANY_PRICE_LIST = "Inter Company"

STATE_CODE_MAP = {
    "01": "Jammu & Kashmir", "02": "Himachal Pradesh", "03": "Punjab",
    "04": "Chandigarh", "05": "Uttarakhand", "06": "Haryana",
    "07": "Delhi", "08": "Rajasthan", "09": "Uttar Pradesh",
    "10": "Bihar", "11": "Sikkim", "12": "Arunachal Pradesh",
    "13": "Nagaland", "14": "Manipur", "15": "Mizoram",
    "16": "Tripura", "17": "Meghalaya", "18": "Assam",
    "19": "West Bengal", "20": "Jharkhand", "21": "Odisha",
    "22": "Chhattisgarh", "23": "Madhya Pradesh", "24": "Gujarat",
    "25": "Daman & Diu", "26": "Dadra & Nagar Haveli",
    "27": "Maharashtra", "28": "Andhra Pradesh (Old)",
    "29": "Karnataka", "30": "Goa", "31": "Lakshadweep",
    "32": "Kerala", "33": "Tamil Nadu", "34": "Puducherry",
    "35": "Andaman & Nicobar Islands", "36": "Telangana",
    "37": "Andhra Pradesh", "38": "Ladakh",
}


class InterCompanyTransfer(StockController):
    def validate(self):
        self.validate_values()
        self.calculate_totals()

    def validate_values(self):
        if self.company == self.to_company:
            frappe.throw(_("From Company and To Company cannot be the same"))

        if not self.transaction_type:
            self.transaction_type = "Inter Company Stock Transfer"

        for item in self.items:
            item.from_warehouse = item.source_warehouse
            item.to_warehouse = item.target_warehouse
            item.rate = flt(item.rate)
            pcs = flt(item.get("fe_pcs", 0))
            if pcs:
                item.qty = pcs
            item.amount = flt(item.amount) or (pcs * flt(item.rate) if pcs else flt(item.qty) * flt(item.rate))

    def calculate_totals(self):
        self.total_qty = 0
        self.total = 0

        for item in self.items:
            self.total_qty += item.qty
            self.total += item.amount

        self.base_grand_total = self.total
        self.grand_total = self.total

    def before_submit(self):
        self.validate_values()
        if not self.items:
            frappe.throw(_("Please add at least one item in the transfer"))
        self.validate_company_accounts()
        self.validate_warehouses()
        self.validate_parties()
        self.status = "Submitted"

    def validate_company_accounts(self):
        """Ensure all required default accounts exist for both companies."""
        for company in [self.company, self.to_company]:
            missing = []
            if not frappe.db.get_value("Company", company, "default_bank_account"):
                missing.append("default Bank Account")
            if not frappe.db.get_value("Company", company, "default_receivable_account"):
                missing.append("default Receivable Account")
            if not frappe.db.get_value("Company", company, "default_payable_account"):
                missing.append("default Payable Account")
            if not frappe.db.get_value("Company", company, "unrealized_profit_loss_account"):
                missing.append("Unrealized Profit Loss Account")
            if missing:
                frappe.throw(_("{0} is missing: {1}").format(
                    company, ", ".join(missing)))

    def validate_warehouses(self):
        """Ensure warehouses belong to the correct companies."""
        for item in self.items:
            wh_company = frappe.db.get_value("Warehouse", item.source_warehouse, "company")
            if wh_company != self.company:
                frappe.throw(_("Warehouse {0} belongs to {1}, not {2}").format(
                    item.source_warehouse, wh_company, self.company))

            wh_company = frappe.db.get_value("Warehouse", item.target_warehouse, "company")
            if wh_company != self.to_company:
                frappe.throw(_("Warehouse {0} belongs to {1}, not {2}").format(
                    item.target_warehouse, wh_company, self.to_company))

    def validate_parties(self):
        """Ensure internal customer and supplier exist for both companies."""
        self.get_internal_customer(self.to_company)
        self.get_internal_supplier(self.company)
        self.get_internal_customer(self.company)
        self.get_internal_supplier(self.to_company)

    def on_submit(self):
        try:
            self.create_intercompany_documents()
        except Exception as e:
            frappe.log_error(
                title=f"ICT Submit Failed: {self.name}",
                message=str(e),
            )
            frappe.throw(
                _("Failed to create inter-company documents: {0}").format(str(e))
            )

    def on_cancel(self):
        self.cancel_generated_documents()
        self.flags.ignore_permissions = True
        self.db_set("status", "Cancelled")

    def cancel_generated_documents(self):
        cancel_order = [
            "Payment Entry", "Purchase Invoice", "Sales Invoice",
            "Purchase Receipt", "Delivery Note",
            "Purchase Order", "Sales Order",
        ]
        for doctype in cancel_order:
            for row in self.generated_documents:
                if row.document_type != doctype or not row.document_name:
                    continue
                doc = frappe.get_doc(row.document_type, row.document_name)
                if doc.docstatus != 1:
                    continue
                try:
                    doc.flags.ignore_links = True
                    doc.flags.ignore_permissions = True
                    doc.flags.ignore_inter_company_validation = True
                    doc.amended_from = doc.name
                    doc.cancel()
                    row.docstatus = 2
                except Exception as e:
                        frappe.log_error(
                            title="ICT Cancel Failed",
                            message=f"Failed to cancel {doctype} {row.document_name}: {e}",
                        )

        self.flags.ignore_permissions = True
        frappe.db.set_value(self.doctype, self.name, "status", "Cancelled")

    def create_intercompany_documents(self):
        if self.transaction_type != "Inter Company Stock Transfer":
            return

        if not self.items:
            frappe.throw(_("Please add at least one item in the transfer"))

        self.clear_linked_docs()

        # Collect fe_ values from ICT items
        fe_data = {}
        for row in self.items:
            if row.item_code:
                fe_data[row.item_code] = {
                    "fe_box": flt(row.get("fe_box", 0)),
                    "fe_pcs": flt(row.get("fe_pcs", 0)),
                    "fe_ltr": flt(row.get("fe_ltr", 0)),
                    "fe_total_ltr": flt(row.get("fe_total_ltr", 0)),
                }

        # Collect doc info before creating (to avoid modifying self during on_submit)
        doc_rows = []

        so = self.create_sales_order()
        so_name = so.name
        doc_rows.append(("Sales Order", so_name, so.company, so.docstatus, self.posting_date, frappe.db.get_value("Sales Order", so_name, "grand_total") or 0))

        po = self.create_purchase_order_from_so(so_name)
        po_name = po.name
        doc_rows.append(("Purchase Order", po_name, po.company, po.docstatus, self.posting_date, frappe.db.get_value("Purchase Order", po_name, "grand_total") or 0))

        dn = self.create_delivery_note_from_so(so_name)
        dn_name = dn.name
        doc_rows.append(("Delivery Note", dn_name, dn.company, dn.docstatus, self.posting_date, frappe.db.get_value("Delivery Note", dn_name, "grand_total") or 0))

        pr = self.create_purchase_receipt_from_dn(dn_name, po_name)
        pr_name = pr.name
        doc_rows.append(("Purchase Receipt", pr_name, pr.company, pr.docstatus, self.posting_date, frappe.db.get_value("Purchase Receipt", pr_name, "grand_total") or 0))

        si = self.create_sales_invoice_from_so(so_name)
        si_name = si.name
        doc_rows.append(("Sales Invoice", si_name, si.company, si.docstatus, self.posting_date, frappe.db.get_value("Sales Invoice", si_name, "grand_total") or 0))

        pi = self.create_purchase_invoice_from_si(si_name)
        pi_name = pi.name
        doc_rows.append(("Purchase Invoice", pi_name, pi.company, pi.docstatus, self.posting_date, frappe.db.get_value("Purchase Invoice", pi_name, "grand_total") or 0))

        # Propagate fe_ values to all created documents
        if fe_data:
            self._propagate_fe_to_doc("Sales Order", so_name, fe_data)
            self._propagate_fe_to_doc("Purchase Order", po_name, fe_data)
            self._propagate_fe_to_doc("Delivery Note", dn_name, fe_data)
            self._propagate_fe_to_doc("Purchase Receipt", pr_name, fe_data)
            self._propagate_fe_to_doc("Sales Invoice", si_name, fe_data)
            self._propagate_fe_to_doc("Purchase Invoice", pi_name, fe_data)

        # Save generated documents to child table via DB only
        frappe.db.set_value(self.doctype, self.name, "status", "Transfer Created")
        
        frappe.db.delete("Inter Company Transfer Generated Document", {"parent": self.name})
        status_map = {0: "Draft", 1: "Submitted", 2: "Cancelled"}
        for (dt, dn, co, ds, pd, gt) in doc_rows:
            frappe.get_doc({
                "doctype": "Inter Company Transfer Generated Document",
                "parent": self.name,
                "parenttype": "Inter Company Transfer",
                "parentfield": "generated_documents",
                "document_type": dt,
                "document_name": dn,
                "company": co,
                "status": status_map.get(ds, "Draft"),
                "posting_date": pd,
                "grand_total": gt,
                "creation": frappe.utils.now(),
            }).db_insert()
        
        frappe.db.commit()

    def _propagate_fe_to_doc(self, doctype, docname, fe_data):
        """Set fe_box/fe_pcs/fe_ltr/fe_total_ltr on items of a created document."""
        if not docname:
            return
        try:
            d = frappe.get_doc(doctype, docname)
            for item in d.items:
                if item.item_code in fe_data:
                    fd = fe_data[item.item_code]
                    item.db_set({
                        "fe_box": fd["fe_box"],
                        "fe_pcs": fd["fe_pcs"],
                        "fe_ltr": fd["fe_ltr"],
                        "fe_total_ltr": fd["fe_total_ltr"],
                    }, update_modified=False)
        except Exception as e:
            frappe.log_error(title=f"ICT propagate fe_ values: {doctype} {docname}", message=str(e))

    def clear_linked_docs(self):
        frappe.db.delete("Inter Company Transfer Generated Document", {"parent": self.name})
        frappe.db.commit()

    # ── Step 1: Sales Order ───────────────────────────────────────────────────
    def create_sales_order(self):
        customer = self.get_internal_customer(self.to_company)

        so = frappe.new_doc("Sales Order")
        so.company = self.company
        so.customer = customer
        so.transaction_date = self.posting_date
        so.delivery_date = self.posting_date
        so.currency = frappe.get_cached_value("Company", self.company, "default_currency") or "INR"
        so.ignore_pricing_rule = 1

        for transfer_item in self.items:
            pcs = flt(transfer_item.get("fe_pcs", 0))
            amount = pcs * flt(transfer_item.rate) if pcs else flt(transfer_item.qty) * flt(transfer_item.rate)
            so.append("items", {
                "item_code": transfer_item.item_code,
                "qty": pcs or transfer_item.qty,
                "rate": transfer_item.rate,
                "amount": amount,
                "warehouse": transfer_item.source_warehouse,
                "delivery_date": self.posting_date,
                "gst_hsn_code": frappe.db.get_value("Item", transfer_item.item_code, "gst_hsn_code") or "",
            })

        if self.sales_tax_template:
            self.apply_tax_template(so, self.sales_tax_template, self.company)

        so.flags.ignore_inter_company_validation = 1
        so.flags.ignore_permissions = True
        so.flags.ignore_links = True
        so.run_method("set_missing_values")
        so.selling_price_list = INTER_COMPANY_PRICE_LIST
        so.run_method("calculate_taxes_and_totals")
        so.save(ignore_permissions=True)
        so.submit()

        self._fix_amounts_after_submit(so, "Sales Order", "Sales Order Item")

        return so

    # ── Step 2: Purchase Order ────────────────────────────────────────────────
    def create_purchase_order_from_so(self, so_name):
        from erpnext.selling.doctype.sales_order.sales_order import make_inter_company_purchase_order

        po = make_inter_company_purchase_order(so_name)
        po.company = self.to_company
        po.supplier = self.get_internal_supplier(self.company)
        po.currency = frappe.get_cached_value("Company", self.to_company, "default_currency") or "INR"
        po.supplier_gstin = frappe.get_cached_value("Company", self.company, "gstin") or ""
        po.gst_category = "Registered Regular"

        company_state = (frappe.get_cached_value("Company", self.to_company, "gstin") or "")[:2]
        if company_state:
            po.place_of_supply = "{0}-{1}".format(company_state, STATE_CODE_MAP.get(company_state, ""))

        for item in po.items:
            for transfer_item in self.items:
                if transfer_item.item_code == item.item_code:
                    item.warehouse = transfer_item.target_warehouse
                    if transfer_item.batch_no:
                        item.batch_no = transfer_item.batch_no
                    pcs = flt(transfer_item.get("fe_pcs", 0))
                    item.amount = pcs * flt(transfer_item.rate) if pcs else flt(transfer_item.qty) * flt(transfer_item.rate)
                    break
            if not item.schedule_date:
                item.schedule_date = self.posting_date

        po.flags.ignore_inter_company_validation = 1
        po.flags.ignore_permissions = True
        po.run_method("set_missing_values")
        po.transaction_date = self.posting_date

        if self.purchase_tax_template:
            self.apply_tax_template(po, self.purchase_tax_template, self.to_company)

        po.buying_price_list = INTER_COMPANY_PRICE_LIST
        po.run_method("calculate_taxes_and_totals")
        po.save(ignore_permissions=True)
        po.submit()

        self._fix_amounts_after_submit(po, "Purchase Order", "Purchase Order Item")

        return po

    # ── Step 3: Delivery Note ─────────────────────────────────────────────────
    def create_delivery_note_from_so(self, so_name):
        from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note

        dn = make_delivery_note(so_name)
        dn.company = self.company

        for item in dn.items:
            for transfer_item in self.items:
                if transfer_item.item_code == item.item_code:
                    item.target_warehouse = transfer_item.target_warehouse
                    item.warehouse = transfer_item.source_warehouse
                    if transfer_item.batch_no:
                        item.batch_no = transfer_item.batch_no
                    break

        dn.flags.ignore_inter_company_validation = 1
        dn.flags.ignore_permissions = True
        dn.run_method("set_missing_values")
        dn.selling_price_list = INTER_COMPANY_PRICE_LIST
        dn.posting_date = self.posting_date
        dn.set_posting_time = 1
        if self.sales_tax_template:
            self.apply_tax_template(dn, self.sales_tax_template, self.company)
        dn.save(ignore_permissions=True)
        dn.submit()

        self._fix_amounts_after_submit(dn, "Delivery Note", "Delivery Note Item")

        return dn

    # ── Step 4: Purchase Receipt ──────────────────────────────────────────────
    def create_purchase_receipt_from_dn(self, dn_name, po_name):
        from erpnext.stock.doctype.delivery_note.delivery_note import make_inter_company_purchase_receipt

        pr = make_inter_company_purchase_receipt(dn_name)
        pr.company = self.to_company
        pr.supplier_gstin = frappe.get_cached_value("Company", self.company, "gstin") or ""
        pr.gst_category = "Registered Regular"
        company_state = (frappe.get_cached_value("Company", self.to_company, "gstin") or "")[:2]
        if company_state:
            pr.place_of_supply = "{0}-{1}".format(company_state, STATE_CODE_MAP.get(company_state, ""))

        po_doc = frappe.get_doc("Purchase Order", po_name)
        po_item_map = {d.item_code: d.name for d in po_doc.items}

        for item in pr.items:
            for transfer_item in self.items:
                if transfer_item.item_code == item.item_code:
                    item.warehouse = transfer_item.target_warehouse
                    if transfer_item.batch_no:
                        item.batch_no = transfer_item.batch_no
                    break
            item.purchase_order = po_name
            if item.item_code in po_item_map:
                item.purchase_order_item = po_item_map[item.item_code]

        pr.flags.ignore_inter_company_validation = 1
        pr.flags.ignore_permissions = True
        pr.run_method("set_missing_values")
        pr.buying_price_list = INTER_COMPANY_PRICE_LIST
        pr.posting_date = self.posting_date
        pr.set_posting_time = 1
        if self.purchase_tax_template:
            self.apply_tax_template(pr, self.purchase_tax_template, self.to_company)
        pr.save(ignore_permissions=True)
        pr.submit()

        self._fix_amounts_after_submit(pr, "Purchase Receipt", "Purchase Receipt Item")

        return pr

    # ── Step 5: Sales Invoice ─────────────────────────────────────────────────
    def create_sales_invoice_from_so(self, so_name):
        from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice

        si = make_sales_invoice(so_name)
        si.company = self.company
        si.customer = self.get_internal_customer(self.to_company)
        si.due_date = self.posting_date
        si.currency = frappe.get_cached_value("Company", self.company, "default_currency") or "INR"
        si.ignore_pricing_rule = 1
        # The app now defaults `update_stock` to 1 on Sale/Purchase Invoice for
        # new manual forms. ICT moves stock via its own process, not through the
        # invoice legs, so force this off -- otherwise both legs would attempt a
        # (warehouse-less) stock posting on submit.
        si.update_stock = 0

        if self.sales_tax_template:
            self.apply_tax_template(si, self.sales_tax_template, self.company)

        si.flags.ignore_inter_company_validation = 1
        si.flags.ignore_permissions = True
        si.flags.ignore_links = True
        si.run_method("set_missing_values")
        si.selling_price_list = INTER_COMPANY_PRICE_LIST
        si.run_method("calculate_taxes_and_totals")
        si.posting_date = self.posting_date
        si.set_posting_time = 1
        si.save(ignore_permissions=True)
        si.submit()

        self._fix_amounts_after_submit(si, "Sales Invoice", "Sales Invoice Item")

        return si

    # ── Step 6: Purchase Invoice ──────────────────────────────────────────────
    def create_purchase_invoice_from_si(self, si_name):
        from erpnext.accounts.doctype.sales_invoice.sales_invoice import make_inter_company_purchase_invoice

        pi = make_inter_company_purchase_invoice(si_name)
        pi.company = self.to_company
        pi.supplier = self.get_internal_supplier(self.company)
        pi.represents_company = frappe.db.get_value("Supplier", pi.supplier, "represents_company")
        pi.company_gstin = frappe.get_cached_value("Company", self.to_company, "gstin") or ""
        pi.supplier_gstin = frappe.get_cached_value("Company", self.company, "gstin") or ""
        pi.gst_category = "Registered Regular"
        pi.bill_no = si_name
        pi.bill_date = self.posting_date
        pi.due_date = self.posting_date
        pi.currency = frappe.get_cached_value("Company", self.to_company, "default_currency") or "INR"

        company_state = (frappe.get_cached_value("Company", self.to_company, "gstin") or "")[:2]
        if company_state:
            pi.place_of_supply = "{0}-{1}".format(company_state, STATE_CODE_MAP.get(company_state, ""))

        pi.taxes = []
        pi.taxes_and_charges = ""
        if self.purchase_tax_template:
            self.apply_tax_template(pi, self.purchase_tax_template, self.to_company)
        # See the matching note on the sales leg above: keep ICT legs from
        # inheriting the app's new `update_stock = 1` default.
        pi.update_stock = 0

        pi.flags.ignore_inter_company_validation = 1
        pi.flags.ignore_permissions = True
        pi.flags.ignore_links = True
        pi.flags.ignore_cash_flow_validation = True
        pi.run_method("set_missing_values")
        pi.buying_price_list = INTER_COMPANY_PRICE_LIST
        pi.run_method("calculate_taxes_and_totals")
        pi.posting_date = self.posting_date
        pi.set_posting_time = 1
        pi.save(ignore_permissions=True)
        pi.submit()

        self._fix_amounts_after_submit(pi, "Purchase Invoice", "Purchase Invoice Item")

        return pi

    # ── Helpers ───────────────────────────────────────────────────────────────

    def apply_tax_template(self, doc, template_name, company):
        if not template_name:
            return

        # Auto-detect doctype from template name (Input = Purchase, Output = Sales)
        if template_name.lower().startswith("input"):
            tax_doctype = "Purchase Taxes and Charges Template"
        elif template_name.lower().startswith("output"):
            tax_doctype = "Sales Taxes and Charges Template"
        elif doc.doctype in ("Sales Order", "Sales Invoice"):
            tax_doctype = "Sales Taxes and Charges Template"
        else:
            tax_doctype = "Purchase Taxes and Charges Template"

        if not frappe.db.exists(tax_doctype, template_name):
            frappe.throw(_("Tax Template {0} not found in {1}").format(template_name, tax_doctype))

        tmpl = frappe.get_doc(tax_doctype, template_name)
        doc.taxes_and_charges = template_name
        doc.taxes = []
        for row in tmpl.taxes:
            doc.append("taxes", {
                "charge_type": row.charge_type,
                "account_head": row.account_head,
                "rate": row.rate,
                "description": row.description,
            })

    def _fix_amounts_after_submit(self, doc, doctype, item_doctype):
        """After submit, force item qty to PCS, amount to pcs*rate, recalculate taxes and grand_total."""
        tax_child_table = "Sales Taxes and Charges" if "Sales" in doctype or "Delivery" in doctype else "Purchase Taxes and Charges"

        for item in doc.items:
            for transfer_item in self.items:
                if transfer_item.item_code == item.item_code:
                    pcs = flt(transfer_item.get("fe_pcs", 0))
                    new_qty = pcs or flt(transfer_item.qty)
                    new_amount = pcs * flt(transfer_item.rate) if pcs else flt(transfer_item.qty) * flt(transfer_item.rate)
                    frappe.db.set_value(item_doctype, item.name, "qty", new_qty, update_modified=False)
                    frappe.db.set_value(item_doctype, item.name, "amount", new_amount, update_modified=False)
                    frappe.db.set_value(item_doctype, item.name, "base_amount", new_amount, update_modified=False)
                    break

        net_total = sum(flt(frappe.db.get_value(item_doctype, it.name, "amount")) for it in doc.items)

        total_tax = 0
        for tax_row in doc.taxes:
            if tax_row.charge_type == "On Net Total" and tax_row.rate:
                tax_amount = net_total * flt(tax_row.rate) / 100
                frappe.db.set_value(tax_child_table, tax_row.name, "tax_amount", tax_amount, update_modified=False)
                frappe.db.set_value(tax_child_table, tax_row.name, "base_tax_amount", tax_amount, update_modified=False)
                total_tax += tax_amount
            elif tax_row.charge_type == "Actual":
                total_tax += flt(tax_row.tax_amount)

        grand_total = net_total + total_tax

        frappe.db.set_value(doctype, doc.name, "net_total", net_total, update_modified=False)
        frappe.db.set_value(doctype, doc.name, "base_net_total", net_total, update_modified=False)
        frappe.db.set_value(doctype, doc.name, "total_taxes_and_charges", total_tax, update_modified=False)
        frappe.db.set_value(doctype, doc.name, "grand_total", grand_total, update_modified=False)
        frappe.db.set_value(doctype, doc.name, "base_grand_total", grand_total, update_modified=False)
        frappe.db.set_value(doctype, doc.name, "rounded_total", round(grand_total), update_modified=False)
        frappe.db.set_value(doctype, doc.name, "base_rounded_total", round(grand_total), update_modified=False)
        frappe.db.commit()

    def get_internal_customer(self, company):
        customer = frappe.db.get_value(
            "Customer",
            {"disabled": 0, "is_internal_customer": 1, "represents_company": company},
            "name",
        )
        if not customer:
            frappe.throw(_("No Internal Customer found representing company {0}. "
                "Please create an Internal Customer with 'Represents Company' = {0}").format(company))
        return customer

    def get_internal_supplier(self, company):
        supplier = frappe.db.get_value(
            "Supplier",
            {"disabled": 0, "is_internal_supplier": 1, "represents_company": company},
            "name",
        )
        if not supplier:
            frappe.throw(_("No Internal Supplier found representing company {0}. "
                "Please create an Internal Supplier with 'Represents Company' = {0}").format(company))
        return supplier

    def get_latest_doc(self, doctype):
        return frappe.db.get_value(
            self.doctype + " Generated Document",
            {"parent": self.name, "document_type": doctype},
            "document_name",
            order_by="creation desc",
        )
