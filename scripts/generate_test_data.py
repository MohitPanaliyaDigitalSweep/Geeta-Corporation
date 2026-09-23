#!/usr/bin/env python3
"""Generate comprehensive test data for all 4 reports + ICT

Usage:
    python scripts/generate_test_data.py [site] [sites_path]

Defaults:
    site        dev.localhost
    sites_path  <bench_root>/sites   (auto-detected from repo location)
"""
import os
import sys
import argparse
import frappe
import random
import math
from datetime import date, timedelta

_here = os.path.dirname(os.path.abspath(__file__))
_default_sites = os.path.join(os.path.dirname(os.path.dirname(_here)), "sites")

_parser = argparse.ArgumentParser(description="Generate Geeta Corporation test data")
_parser.add_argument("site", nargs="?", default="dev.localhost")
_parser.add_argument("sites_path", nargs="?", default=_default_sites)
_args = _parser.parse_args()

frappe.init(_args.site, sites_path=_args.sites_path)
frappe.connect()

# ============================================================
# CONFIGURATION
# ============================================================
COMPANY = "Geeta Corporation"
COMPANY_ABBR = "GC"
COMPANY_GSTIN = "24AAACG2115R1ZN"
COMPANY_STATE = "Gujarat"
COMPANY_STATE_CODE = "24"

OTHER_COMPANY = "GLOBAL OIL CORPORATION"
OTHER_COMPANY_ABBR = "GOC"
OTHER_COMPANY_GSTIN = "24AAACG2115R1Z5"

SALES_PERSONS = ["Imran Sales Boy", "Mohit Sales Person"]

ITEMS = [
    ("1404184", "SERVO PRIDE 40 - 20x1L - HDPE", 250, 20, 1.0),
    ("1404234", "SERVO PRIDE 40 - 4x5L - HDPE", 250, 4, 5.0),
    ("1404265", "SERVO PRIDE 40-20L BUC", 250, 1, 20.0),
    ("2502174", "SERVO GEAR HP 90-40X1/2L-HDPE", 220, 40, 0.5),
    ("2502184", "SERVO GEAR HP 90-20X1L-HDPE", 220, 20, 1.0),
    ("2502234", "SERVO GEAR HP 90 - 4x5L - HDPE", 220, 4, 5.0),
    ("2502265", "SERVO GEAR HP 90-20L BUC", 220, 1, 20.0),
    ("7849339", "SERVO LONG LIFE GREASE-5 KG", 180, 1, 5.0),
    ("7849341", "SERVO LONG LIFE GREASE-20 KG", 180, 1, 20.0),
    ("7849313", "SERVO LONG LIFE GREASE-10X1 KG TUB", 180, 10, 1.0),
    ("8128451", "SERVOGREASE WR2 - 182 KG DRUM", 350, 1, 182.0),
    ("7903451", "SERVOGREASE MIRACLE 3-182 KG", 380, 1, 182.0),
]

# Customers with addresses, pincodes, party groups
CUSTOMERS = [
    {
        "name": "HARIOM PETROLEUM",
        "gstin": "",
        "address": "NH-48, OPP BOMBAY MARKET, UTRAN",
        "city": "surat",
        "pincode": "394107",
        "state": "Gujarat",
        "party_group": "Mohit Petrol Pump",
    },
    {
        "name": "SHANTABA PETROLEUM",
        "gstin": "",
        "address": "AT POST OLPAD, BOLAV",
        "city": "surat",
        "pincode": "394540",
        "state": "Gujarat",
        "party_group": "Mohit Petrol Pump",
    },
    {
        "name": "HIGHWAY AUTO CENTRE",
        "gstin": "",
        "address": "NH-08, KAMREJ CHAR RASTA",
        "city": "surat",
        "pincode": "394185",
        "state": "Gujarat",
        "party_group": "Mohit Petrol Pump",
    },
    {
        "name": "GUJARAT PETROLEUM COMPANY",
        "gstin": "",
        "address": "FP NO. 58/P, R.S.NO. 109/1 2, ADAJAN",
        "city": "surat",
        "pincode": "395005",
        "state": "Gujarat",
        "party_group": "IOCL",
    },
    {
        "name": "GAJANAND PETROLEUM",
        "gstin": "",
        "address": "BLOCK NO.134/A, SURVEY NO.24/10",
        "city": "surat",
        "pincode": "394107",
        "state": "Gujarat",
        "party_group": "IOCL",
    },
    {
        "name": "EKLAVYA PETROLEUM",
        "gstin": "",
        "address": "G.F. SURVEY NO.503, KAMREJ",
        "city": "surat",
        "pincode": "394185",
        "state": "Gujarat",
        "party_group": "IOCL",
    },
    {
        "name": "C D PETROLEUM",
        "gstin": "",
        "address": "GROUND FLOOR 93, NIRMAL NAGAR",
        "city": "surat",
        "pincode": "395006",
        "state": "Gujarat",
        "party_group": "Mohit Petrol Pump",
    },
    {
        "name": "BHAVYA CORPORATION",
        "gstin": "",
        "address": "IOC DEALER, OLPAD",
        "city": "surat",
        "pincode": "394540",
        "state": "Gujarat",
        "party_group": "IOCL",
    },
    {
        "name": "AASHTHA PETROLEUM",
        "gstin": "",
        "address": "540, SWAGAT ESTATE, SURAT TO OLPAD",
        "city": "surat",
        "pincode": "394540",
        "state": "Gujarat",
        "party_group": "Mohit Petrol Pump",
    },
    {
        "name": "DHANSUKHLAL C. SHAH",
        "gstin": "",
        "address": "AT & POST MANDAVI, MANDAVI",
        "city": "surat",
        "pincode": "394160",
        "state": "Gujarat",
        "party_group": "Mohit Petrol Pump",
    },
    # Out of state customers for IGST testing
    {
        "name": "RAJASTHAN OIL TRADERS",
        "gstin": "",
        "address": "NEAR PETROL PUMP, JAIPUR",
        "city": "jaipur",
        "pincode": "302001",
        "state": "Rajasthan",
        "party_group": "IOCL",
    },
    {
        "name": "MAHARASHTRA FUEL CORP",
        "gstin": "",
        "address": "ANDHERI EAST, MUMBAI",
        "city": "mumbai",
        "pincode": "400069",
        "state": "Maharashtra",
        "party_group": "IOCL",
    },
]

# State code mapping
STATE_CODES = {
    "Gujarat": "24", "Rajasthan": "08", "Maharashtra": "27",
    "Madhya Pradesh": "23", "Karnataka": "29", "Tamil Nadu": "33",
}

# ============================================================
# HELPER FUNCTIONS
# ============================================================
def get_address_name(customer_name):
    """Get address name for customer"""
    result = frappe.db.sql(
        """SELECT dl.parent FROM `tabDynamic Link` dl 
        WHERE dl.link_doctype='Customer' AND dl.link_name=%s 
        AND dl.parenttype='Address' LIMIT 1""",
        customer_name, as_dict=True
    )
    return result[0].parent if result else None

def create_customer(cust_data):
    """Create or get customer with address"""
    name = cust_data["name"]
    
    # Create customer if not exists
    if not frappe.db.exists("Customer", name):
        doc = frappe.new_doc("Customer")
        doc.customer_name = name
        doc.customer_group = "Commercial"
        doc.territory = "India"
        doc.tax_id = ""
        doc.customer_type = "Company"
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        print(f"  Created customer: {name}")
    
    # Create address if not exists
    addr_name = f"{name}-Billing"
    if not frappe.db.exists("Address", addr_name):
        doc = frappe.new_doc("Address")
        doc.address_title = name
        doc.address_type = "Billing"
        doc.address_line1 = cust_data["address"]
        doc.city = cust_data["city"]
        doc.pincode = cust_data["pincode"]
        doc.country = "India"
        doc.state = cust_data["state"]
        doc.gst_state = cust_data["state"]
        doc.gst_state_number = STATE_CODES.get(cust_data["state"], "24")
        doc.gstin = ""
        doc.phone = f"98{random.randint(10000000, 99999999)}"
        doc.append("links", {"link_doctype": "Customer", "link_name": name})
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        print(f"  Created address: {addr_name}")
    
    # Assign to party group
    pg_name = cust_data.get("party_group")
    if pg_name and frappe.db.exists("Party Group", pg_name):
        existing = frappe.db.sql(
            """SELECT name FROM `tabParty Group Party` 
            WHERE parent=%s AND party_name=%s""",
            (pg_name, name), as_dict=True
        )
        if not existing:
            pg = frappe.get_doc("Party Group", pg_name)
            pg.append("parties", {"party_type": "Customer", "party": name})
            pg.save(ignore_permissions=True)
            frappe.db.commit()
            print(f"  Added {name} to party group {pg_name}")
    
    return name

def create_sales_invoice(company, customer, posting_date, items_data, sales_person, tax_type="intra"):
    """Create and submit a Sales Invoice"""
    doc = frappe.new_doc("Sales Invoice")
    doc.company = company
    doc.customer = customer
    doc.posting_date = posting_date
    doc.currency = "INR"
    doc.price_list_name = "Standard Selling"
    doc.selling_price_list = "Standard Selling"
    
    # Set customer address
    addr = get_address_name(customer)
    if addr:
        doc.customer_address = addr
        doc.address_display = frappe.db.get_value("Address", addr, "address_line1")
    
    # Set company address
    company_addr = frappe.db.sql(
        """SELECT dl.parent FROM `tabDynamic Link` dl
        WHERE dl.link_doctype='Company' AND dl.link_name=%s 
        AND dl.parenttype='Address' LIMIT 1""",
        company, as_dict=True
    )
    if company_addr:
        doc.company_address = company_addr[0].name
    
    # Add items
    total = 0
    for item_code, item_name, rate, qty, ltr in items_data:
        item_doc = doc.append("items", {
            "item_code": item_code,
            "item_name": item_name,
            "qty": qty,
            "rate": rate,
            "amount": qty * rate,
            "warehouse": f"Finished Goods - {COMPANY_ABBR}",
            "income_account": f"Sales - {COMPANY_ABBR}",
        })
        # Set fe_* fields
        box = math.ceil(qty / 20) if qty > 1 else 1
        pcs = qty
        total_ltr = qty * ltr
        frappe.db.set_value("Sales Invoice Item", item_doc.name, "fe_box", box)
        frappe.db.set_value("Sales Invoice Item", item_doc.name, "fe_pcs", pcs)
        frappe.db.set_value("Sales Invoice Item", item_doc.name, "fe_ltr", ltr)
        frappe.db.set_value("Sales Invoice Item", item_doc.name, "fe_total_ltr", total_ltr)
        total += qty * rate
    
    # Add sales person
    doc.append("sales_team", {
        "sales_person": sales_person,
        "allocated_percentage": 100,
    })
    
    # Calculate taxes
    doc.run_method("calculate_taxes_and_totals")
    
    # Insert and submit
    doc.insert(ignore_permissions=True)
    doc.submit()
    frappe.db.commit()
    print(f"  Created SI: {doc.name} | {customer} | {posting_date} | {total}")
    return doc.name

def create_ict(company_from, company_to, customer_from, customer_to, posting_date, items_data):
    """Create and submit an Inter Company Transfer"""
    doc = frappe.new_doc("Inter Company Transfer")
    doc.company = company_from
    doc.customer = customer_from
    doc.to_company = company_to
    doc.posting_date = posting_date
    doc.mode_of_transfer = "Bill to Ship to"
    doc.source_warehouse = f"Finished Goods - {COMPANY_ABBR}"
    doc.target_warehouse = f"Finished Goods - {OTHER_COMPANY_ABBR}"
    
    # Set fe_pcs = qty for each item
    total_pcs = 0
    total_ltr = 0
    total_boxes = 0
    for item_code, item_name, rate, qty, ltr in items_data:
        pcs = qty
        box = math.ceil(pcs / 20) if pcs > 1 else 1
        item_ltr = pcs * ltr
        doc.append("items", {
            "item_code": item_code,
            "item_name": item_name,
            "qty": pcs,
            "rate": rate,
            "amount": pcs * rate,
            "fe_box": box,
            "fe_pcs": pcs,
            "fe_ltr": ltr,
            "fe_total_ltr": item_ltr,
            "warehouse": f"Finished Goods - {COMPANY_ABBR}",
        })
        total_pcs += pcs
        total_ltr += item_ltr
        total_boxes += box
    
    # Set tax templates
    doc.seller_tax_template = f"Output GST In-state - {COMPANY_ABBR}"
    doc.buyer_tax_template = f"Input GST In-state - {OTHER_COMPANY_ABBR}"
    doc.gst_category = "Registered Regular"
    
    doc.insert(ignore_permissions=True)
    doc.submit()
    frappe.db.commit()
    print(f"  Created ICT: {doc.name} | {posting_date} | PCS={total_pcs} | Ltr={total_ltr}")
    return doc.name

def create_delivery_note(company, customer, posting_date, si_name, items_data):
    """Create and submit a Delivery Note"""
    doc = frappe.new_doc("Delivery Note")
    doc.company = company
    doc.customer = customer
    doc.posting_date = posting_date
    
    addr = get_address_name(customer)
    if addr:
        doc.customer_address = addr
    
    doc.set_warehouse = f"Finished Goods - {COMPANY_ABBR}"
    
    for item_code, item_name, rate, qty, ltr in items_data:
        doc.append("items", {
            "item_code": item_code,
            "item_name": item_name,
            "qty": qty,
            "rate": rate,
            "amount": qty * rate,
            "warehouse": f"Finished Goods - {COMPANY_ABBR}",
        })
    
    doc.insert(ignore_permissions=True)
    doc.submit()
    frappe.db.commit()
    print(f"  Created DN: {doc.name} | {customer} | {posting_date}")
    return doc.name

# ============================================================
# MAIN DATA GENERATION
# ============================================================
print("=" * 60)
print("GENERATING COMPREHENSIVE TEST DATA")
print("=" * 60)

# Step 1: Create customers
print("\n--- Step 1: Creating customers ---")
for cust in CUSTOMERS:
    create_customer(cust)

# Step 2: Generate monthly Sales Invoices for 2 years
print("\n--- Step 2: Generating monthly Sales Invoices (2024-2026) ---")
random.seed(42)  # For reproducible data

months = []
for year in [2024, 2025, 2026]:
    end_month = 9 if year == 2026 else 12
    for month in range(1, end_month + 1):
        months.append((year, month))

si_count = 0
dn_count = 0
for year, month in months:
    # Generate 3-6 invoices per month
    num_invoices = random.randint(3, 6)
    for i in range(num_invoices):
        # Random day in month
        day = random.randint(1, 28)
        posting_date = date(year, month, day)
        
        # Random customer
        cust_data = random.choice(CUSTOMERS)
        customer = cust_data["name"]
        
        # Random sales person
        sp = random.choice(SALES_PERSONS)
        
        # Random 2-4 items
        num_items = random.randint(2, 4)
        selected_items = random.sample(ITEMS, num_items)
        items_data = []
        for item_code, item_name, rate, pcs, ltr in selected_items:
            qty = random.randint(1, pcs * 5)
            items_data.append((item_code, item_name, rate, qty, ltr))
        
        # Create SI
        try:
            si_name = create_sales_invoice(
                COMPANY, customer, posting_date, items_data, sp
            )
            si_count += 1
            
            # Create DN for ~70% of invoices
            if random.random() < 0.7:
                try:
                    create_delivery_note(
                        COMPANY, customer, posting_date + timedelta(days=2),
                        si_name, items_data
                    )
                    dn_count += 1
                except Exception as e:
                    print(f"  DN Error: {e}")
        except Exception as e:
            print(f"  SI Error: {e}")

print(f"\nCreated {si_count} Sales Invoices, {dn_count} Delivery Notes")

# Step 3: Generate ICT entries
print("\n--- Step 3: Generating ICT entries ---")
ict_count = 0
for year, month in months:
    # 1-2 ICTs per month
    num_icts = random.randint(1, 2)
    for i in range(num_icts):
        day = random.randint(1, 28)
        posting_date = date(year, month, day)
        
        # Random 1-3 items
        num_items = random.randint(1, 3)
        selected_items = random.sample(ITEMS, num_items)
        items_data = []
        for item_code, item_name, rate, pcs, ltr in selected_items:
            qty = random.randint(1, pcs * 3)
            items_data.append((item_code, item_name, rate, qty, ltr))
        
        try:
            create_ict(
                COMPANY, OTHER_COMPANY,
                f"Internal Customer - {OTHER_COMPANY_ABBR}",
                f"Internal Customer - {COMPANY_ABBR}",
                posting_date, items_data
            )
            ict_count += 1
        except Exception as e:
            print(f"  ICT Error: {e}")

print(f"\nCreated {ict_count} ICT entries")

# ============================================================
# SUMMARY
# ============================================================
print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)

si_total = frappe.db.count("Sales Invoice", {"docstatus": 1})
dn_total = frappe.db.count("Delivery Note", {"docstatus": 1})
ict_total = frappe.db.count("Inter Company Transfer", {"docstatus": 1})
cust_total = frappe.db.count("Customer")

print(f"Total Customers: {cust_total}")
print(f"Total Sales Invoices: {si_total}")
print(f"Total Delivery Notes: {dn_total}")
print(f"Total ICT: {ict_total}")
print(f"\nDate range: {months[0][0]}-{months[0][1]:02d} to {months[-1][0]}-{months[-1][1]:02d}")
print(f"Sales Persons: {', '.join(SALES_PERSONS)}")
print(f"Party Groups: Mohit Petrol Pump, IOCL")
print(f"Companies: {COMPANY}, {OTHER_COMPANY}")

frappe.destroy()
print("\nDone!")
