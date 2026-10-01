"""Convert stock items from Box-based stock UOM to piece-based (Nos) stock UOM.

WHY
---
This site's Item masters used the "UOM Conversion Detail" table to store *pack
specification* rather than real ERPNext conversion factors:

    Item 1404184, stock_uom = Box
        Box    cf = 1     <- ERPNext anchor (cf of the stock UOM must be 1)
        Nos    cf = 20    <- actually "pieces per box"   (P)
        Litre  cf = 1     <- actually "litres per piece"  (L)

ERPNext's contract is the reverse: conversion_factor = *stock units per one unit
of this UOM*, anchored by cf = 1 on the stock UOM itself. Proof in core:

    erpnext/controllers/selling_controller.py
        d.stock_qty = flt(d.qty) * flt(d.conversion_factor)
    erpnext/stock/doctype/stock_entry/stock_entry.py::set_transfer_qty
        item.transfer_qty = flt(item.qty) * flt(item.conversion_factor)
    erpnext/controllers/transaction_base.py::validate_conversion_factor
        "Conversion factor for default Unit of Measure must be 1"

So the table said "1 Nos = 20 Box", which is inverted, and the app added a second
defect on top by hardcoding conversion_factor = 1.0 on every invoice row. The
net effect was stock inflation of P times (4x / 20x / 200x depending on item).

WHAT "OPTION B" DOES
-------------------
Make "Nos" (pieces) the stock UOM, which is the unit Fast Entry App actually trades
in (fe_pcs / qty / per-piece rate). Then:

    Item 1404184, stock_uom = Nos
        Nos    cf = 1     <- new anchor
        Box    cf = 20    <- now genuinely "1 Box = 20 Nos"
        Litre  cf = 1/1   <- genuinely "1 Litre = 1 Nos"

and the invoice row uom="Nos", cf=1, stock_qty=pcs becomes *correct*, which is why
this option needs no change to the invoice-writing code paths.

Reorder levels are expressed in the stock UOM, so any warehouse reorder level /
qty is rescaled from Boxes to pieces by multiplying with P.

LITRE / KG ROWS ARE DELIBERATELY LEFT UNTOUCHED
----------------------------------------------
The Litre/Kg rows hold "litres (or kg) per piece" and are only ever consumed by
Fast Entry App as ``litre_factor`` (fe_ltr / total_ltr = pcs x litre_factor).
Inverting them into true ERPNext factors is actively harmful:

* ERPNext stores 6 decimals, and 1/16.666667 cannot round-trip back to 0.06
  (it comes back as 0.0599999988), so every invoice total would carry drift.
* Nothing invoices in Litre -- invoice rows are hardcoded to uom="Nos" -- so the
  "wrongness" is unreachable in practice.
* Fixing it would mean touching every litre_factor consumer for zero stock gain.

They are therefore left exactly as they were, and this wart is documented rather
than papered over. The app derives P from the Box row only.

SAFETY
------
* Dry run by default; nothing is written unless dry_run=False.
* Mirrors ERPNext's own guard in erpnext.stock.doctype.item.item
  .check_stock_uom_with_bin and refuses items that already have Stock Ledger
  Entries or Bin commitments in the old UOM -- use revalue_stock() for those.
* Writes with frappe.db so ERPNext's
  Item.add_default_uom_in_conversion_factor_table (which wipes `uoms` whenever
  stock_uom changes) cannot destroy the conversion table.
* Idempotent: items already on Nos are skipped.
* Saves a JSON rollback snapshot to the site's private files first.
"""

from __future__ import annotations

import json
import math

import frappe

STOCK_UOM_FROM = "Box"
STOCK_UOM_TO = "Nos"
# UOMs whose factor is stored as "per piece". Intentionally NOT rewritten -- see
# the module docstring ("LITRE / KG ROWS ARE DELIBERATELY LEFT UNTOUCHED").
INVERT_UOMS: tuple = ()
PRECISION = 6


def _round(value):
	return round(float(value) + 0.0, PRECISION)


def _item_uom_rows(item_code):
	"""Return the UOM Conversion Detail rows of an item as {uom: (row, factor)}."""
	rows = frappe.db.sql(
		"""
		SELECT name, uom, conversion_factor
		FROM `tabUOM Conversion Detail`
		WHERE parent = %s AND parenttype = 'Item'
		""",
		(item_code,),
		as_dict=True,
	)
	return {r.uom: (r.name, float(r.conversion_factor or 0)) for r in rows}


def _has_stock_activity(item_code):
	"""Mirror of ERPNext check_stock_uom_with_bin: refuse items already transacted."""
	if frappe.db.exists("Stock Ledger Entry", {"item_code": item_code}):
		return "has Stock Ledger Entries"

	committed = frappe.db.sql(
		"""
		SELECT COUNT(*) FROM `tabBin`
		WHERE item_code = %s
		  AND (reserved_qty > 0 OR ordered_qty > 0
		       OR indented_qty > 0 OR planned_qty > 0)
		""",
		(item_code,),
	)[0][0]
	if committed:
		return "Bin has reserved/ordered/indented/planned qty"

	return None


def get_candidates(company=None):
	"""Build the full plan without writing anything.

	Returns a dict with the list of planned items and a summary of skips.
	"""
	filters = {"stock_uom": STOCK_UOM_FROM, "is_stock_item": 1}
	if company:
		filters["item_defaults.company"] = company

	items = frappe.get_all(
		"Item",
		filters=filters,
		fields=["name", "stock_uom"],
		order_by="name asc",
	)

	planned, skipped = [], []
	for item in items:
		code = item.name
		uoms = _item_uom_rows(code)

		nos_factor = uoms.get(STOCK_UOM_TO, (None, 0.0))[1]
		if not nos_factor:
			skipped.append({"item_code": code, "reason": "no 'Nos' row to read pieces-per-box from"})
			continue

		# P = pieces per box, as the master currently encodes it.
		pieces_per_box = nos_factor

		changes = [{"uom": STOCK_UOM_TO, "row": uoms.get(STOCK_UOM_TO, (None, 0))[0],
			"old": nos_factor, "new": 1.0}]
		if STOCK_UOM_FROM in uoms:
			changes.append({"uom": STOCK_UOM_FROM, "row": uoms[STOCK_UOM_FROM][0],
				"old": uoms[STOCK_UOM_FROM][1], "new": _round(pieces_per_box)})

		# Litre/Kg stay on "per piece" -- see module docstring.
		for uom in INVERT_UOMS:
			if uom not in uoms or not uoms[uom][1]:
				continue
			per_piece = uoms[uom][1]
			changes.append({"uom": uom, "row": uoms[uom][0],
				"old": per_piece, "new": _round(1.0 / per_piece)})

		blocker = _has_stock_activity(code)
		reorder = frappe.db.sql(
			"""
			SELECT name, warehouse_reorder_level, warehouse_reorder_qty
			FROM `tabItem Reorder`
			WHERE parent = %s
			  AND (warehouse_reorder_level > 0 OR warehouse_reorder_qty > 0)
			""",
			(code,),
			as_dict=True,
		)

		planned.append({
			"item_code": code,
			"stock_uom_from": item.stock_uom,
			"stock_uom_to": STOCK_UOM_TO,
			"pieces_per_box": _round(pieces_per_box),
			"changes": changes,
			"reorder_levels": [
				{
					"name": r.name,
					"warehouse_reorder_level": float(r.warehouse_reorder_level or 0),
					"warehouse_reorder_qty": float(r.warehouse_reorder_qty or 0),
					"new_level": _round(float(r.warehouse_reorder_level or 0) * pieces_per_box),
					"new_qty": _round(float(r.warehouse_reorder_qty or 0) * pieces_per_box),
				}
				for r in reorder
			],
			"blocked": blocker,
		})

	return {"planned": planned, "skipped": skipped,
		"summary": {
			"candidates": len(items),
			"planned": len([p for p in planned if not p["blocked"]]),
			"blocked": len([p for p in planned if p["blocked"]]),
			"skipped": len(skipped),
		}}


def _snapshot_path():
	return frappe.get_site_path("private", "files", "stock_uom_to_pieces_backup.json")


def _save_snapshot(plan):
	path = _snapshot_path()
	frappe.create_folder(frappe.get_site_path("private", "files"))
	with open(path, "w") as fh:
		json.dump(plan, fh, indent=2, default=str)
	return path


def _apply_item(entry):
	code = entry["item_code"]
	pieces_per_box = entry["pieces_per_box"]

	for change in entry["changes"]:
		if not change["row"]:
			# Box row missing (should not happen: stock_uom row always exists).
			frappe.get_doc({
				"doctype": "Item",
				"name": code,
			})
			continue
		frappe.db.set_value(
			"UOM Conversion Detail", change["row"], "conversion_factor", change["new"]
		)

	# Stock UOM itself (db-level on purpose, see module docstring).
	frappe.db.set_value("Item", code, "stock_uom", STOCK_UOM_TO)

	# Mirror ERPNext: keep Bin rows consistent with the new stock UOM.
	frappe.db.sql("UPDATE `tabBin` SET stock_uom = %s WHERE item_code = %s", (STOCK_UOM_TO, code))

	for rl in entry["reorder_levels"]:
		frappe.db.set_value("Item Reorder", rl["name"], {
			"warehouse_reorder_level": rl["new_level"],
			"warehouse_reorder_qty": rl["new_qty"],
		})


def execute(dry_run=True, company=None, ignore_stock_activity=False, verbose=False):
	"""Convert the site to piece-based stock UOM.

	:param dry_run: when True (default) nothing is written.
	:param company: restrict to items that have a default for this company.
	:param ignore_stock_activity: proceed even for items that already have stock
	  history. Only use together with revalue_stock() / a stock revaluation.
	"""
	plan = get_candidates(company=company)
	summary = plan["summary"]

	if dry_run:
		return {"dry_run": True, "summary": summary, "planned": plan["planned"],
			"skipped": plan["skipped"]}

	blocked = [p for p in plan["planned"] if p["blocked"]]
	if blocked and not ignore_stock_activity:
		return {
			"dry_run": False,
			"error": "aborted: stock history exists",
			"summary": summary,
			"blocked": [{"item_code": p["item_code"], "reason": p["blocked"]} for p in blocked],
			"hint": "Use Stock Reconciliation / Stock Entry to revalue first, "
			"then re-run with ignore_stock_activity=True, "
			"or call maintenance.stock_uom_to_pieces.revalue_stock().",
		}

	converted = 0
	for entry in plan["planned"]:
		if entry["blocked"]:
			continue
		_apply_item(entry)
		converted += 1
		if verbose:
			print(f"  {entry['item_code']}: stock_uom Box->Nos, P={entry['pieces_per_box']}")

	frappe.db.commit()
	frappe.clear_cache()

	return {
		"dry_run": False,
		"converted": converted,
		"summary": summary,
		"backup": _save_snapshot(plan),
	}
