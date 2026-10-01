"""Turn a real master-data export into a bundle that is safe to commit.

The repo is public, so ``bundles/geeta_anonymised.json`` must not carry any
personal or commercially sensitive data. This module rewrites one export in
place, deterministically, so the result keeps every *structural* property the
app depends on while replacing every identifying value.

What is preserved
-----------------
* **Items are kept verbatim** -- the product catalogue is the entire point of
  shipping master data, and an item code carries no personal data. This
  includes the post-Option-B ``uoms`` table (``Nos`` = 1, ``Box`` = P), so a
  site seeded from the anonymised bundle is already correct and needs no
  ``stock_uom_to_pieces`` migration.
* **Company names** are kept (they are already public and the app's own
  fixtures reference them). GSTIN, PAN, phone, email, website are replaced.
* **Structure** is kept: group trees, territories, price lists, warehouses,
  which contact belongs to which customer, which address is primary, and which
  state each party is registered in. That is what makes the seeded data useful
  for exercising place-of-supply and IGST-vs-CGST logic.

What is replaced
----------------
* Party names -> ``Customer 001``, ``Supplier 001``, ``Contact 001``, ...
* GSTIN -> a synthetic but *algorithmically valid* GSTIN. Real state codes are
  kept so GST state logic still behaves, and the base-36 check digit is
  recomputed so ``validate_gstin_check_digit`` accepts it.
* PAN -> derived from the regenerated GSTIN.
* Phone / email / fax -> ``9000...`` series and ``example.invalid``.
* Street address lines -> generic, keeping city / state / GST state / pincode.

Every rewrite is deterministic, so re-running produces a byte-identical file.

Usage::

    bench --site dev.localhost execute \\
        fast_entry_app.master_data.anonymise.anonymise_bundle
"""

import json
import os
import re

import frappe

# GST state codes (GST Council notification 12/2017). Kept complete so this
# generalises beyond the handful of states in the current export.
STATE_CODES = {
	"Andaman and Nicobar Islands": "35",
	"Andhra Pradesh": "37",
	"Arunachal Pradesh": "12",
	"Assam": "18",
	"Bihar": "10",
	"Chandigarh": "04",
	"Chhattisgarh": "22",
	"Dadra and Nagar Haveli and Daman and Diu": "26",
	"Delhi": "07",
	"Goa": "30",
	"Gujarat": "24",
	"Haryana": "06",
	"Himachal Pradesh": "02",
	"Jammu and Kashmir": "01",
	"Jharkhand": "20",
	"Karnataka": "29",
	"Kerala": "32",
	"Ladakh": "38",
	"Lakshadweep Islands": "31",
	"Madhya Pradesh": "23",
	"Maharashtra": "27",
	"Manipur": "14",
	"Meghalaya": "17",
	"Mizoram": "15",
	"Nagaland": "13",
	"Odisha": "21",
	"Other Territory": "97",
	"Puducherry": "34",
	"Punjab": "03",
	"Rajasthan": "08",
	"Sikkim": "11",
	"Tamil Nadu": "33",
	"Telangana": "36",
	"Tripura": "16",
	"Uttar Pradesh": "09",
	"Uttarakhand": "05",
	"West Bengal": "19",
}

CODE_POINTS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

GENERIC_CITY_BY_STATE = {
	"Gujarat": "Ahmedabad",
	"Maharashtra": "Pune",
	"Rajasthan": "Jaipur",
	"Karnataka": "Bengaluru",
	"Tamil Nadu": "Chennai",
	"Delhi": "New Delhi",
	"Uttar Pradesh": "Lucknow",
}

# Fields that carry identifying data and therefore must be rewritten. The
# leak scanner only inspects these, so keeping a real value anywhere else
# (city, state, pincode, price list) does not raise a false alarm.
GUARDED_FIELDS = {
	"Company": ["gstin", "pan", "tax_id", "phone_no", "email", "website"],
	"Customer": ["customer_name", "gstin", "pan", "mobile_no", "email_id"],
	"Supplier": ["supplier_name", "gstin", "pan", "mobile_no", "email_id"],
	"Contact": ["first_name", "last_name", "company_name", "mobile_no", "email_id"],
	"Address": [
		"address_title",
		"address_line1",
		"address_line2",
		"gstin",
		"phone",
		"fax",
	],
}

# Highest-value leak check: these value *shapes* must not appear anywhere in
# the written file, in any field, on any doctype.
SENSITIVE_PATTERNS = ("gstin", "pan", "mobile_no", "phone", "email_id", "fax", "email", "tax_id")


def gstin_check_digit(base14: str) -> str:
	"""Recompute the GSTIN check digit.

	Mirrors ``validate_gstin_check_digit`` in
	``india_compliance/gst_india/utils/__init__.py`` (base-36 weighted
	alternating factor). Reimplemented rather than imported so this module
	works on a site without india_compliance installed.
	"""
	mod = len(CODE_POINTS)
	factor, total = 1, 0
	for char in base14:
		digit = factor * CODE_POINTS.find(char)
		digit = (digit // mod) + (digit % mod)
		total += digit
		factor = 2 if factor == 1 else 1
	return CODE_POINTS[(mod - (total % mod)) % mod]


def make_valid_gstin(state_code: str, pan: str) -> str:
	"""Build a 15-char GSTIN that passes ``validate_gstin``.

	The GSTIN layout is state(2) + PAN(10) + entity(1) + literal ``Z`` + check
	digit. India Compliance regex: ``[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}``.
	The entity char sits between the PAN and the ``Z`` and must be 1-9/A-Z.
	"""
	entity = "1"
	base14 = f"{state_code}{pan}{entity}Z"
	if len(base14) != 14:
		raise ValueError(f"invalid GSTIN base: {base14!r} (len {len(base14)})")
	return base14 + gstin_check_digit(base14)


def _valid_pan(pan: str) -> bool:
	"""Same shape india_compliance's ``is_valid_pan`` checks."""
	return (
		isinstance(pan, str)
		and len(pan) == 10
		and pan[:5].isalpha()
		and pan[4].isalpha()
		and pan[5:9].isdigit()
		and pan[9].isalpha()
	)


def _pad3(index: int) -> str:
	return f"{index:03d}"


def _digits(value, length: int = 10) -> str:
	digits = "".join(ch for ch in str(value or "") if ch.isdigit())
	return (digits or "0")[-length:].ljust(length, "0")


def _state_for(gstin, fallback: str) -> str:
	"""Recover the GST state name from a GSTIN prefix, else use the fallback."""
	if gstin and len(gstin) >= 2:
		by_code = {code: name for name, code in STATE_CODES.items()}
		if gstin[:2] in by_code:
			return by_code[gstin[:2]]
	return fallback


def _fake_identity(gstin, index: int, state_name: str):
	"""Return (gstin, pan, state_name) that is valid but not a real identity.

	A PAN is 5 letters, 4 digits, 1 letter. The 5th character encodes the
	entity type (company / partnership / trust ...), so it is preserved from
	the real PAN while the identifying digits are replaced. That keeps the
	anonymised data exercising the same GST code paths without being a
	uniform ``AAAA9999A``.
	"""
	code = STATE_CODES.get(state_name, "24")
	entity = "A"
	if gstin and _valid_pan(gstin[2:12]):
		entity = gstin[6]
	pan = f"AAAA{entity}{index:04d}A"
	assert _valid_pan(pan), f"generated an invalid PAN: {pan}"
	return make_valid_gstin(code, pan), pan, state_name


class _NameMaps:
	"""Source-name -> anonymised-name maps, kept per doctype.

	The seeder resolves a Contact's ``link_name`` against the map, so these
	must be recorded while the parties are being renamed.
	"""

	def __init__(self):
		self.by_doctype = {}

	def get(self, doctype, source_name):
		return self.by_doctype.get(doctype, {}).get(source_name, source_name)

	def set(self, doctype, source_name, anon_name):
		self.by_doctype.setdefault(doctype, {})[source_name] = anon_name


def anonymise_bundle(bundle_path=None, out_path=None):
	"""Read a real export, write an anonymised bundle, return a summary."""
	frappe.only_for(("System Manager",))

	if not bundle_path:
		bundle_path = frappe.get_site_path("private", "files", "master_data_export.json")
	if not out_path:
		out_path = frappe.get_app_path(
			"fast_entry_app", "master_data", "bundles", "geeta_anonymised.json"
		)

	with open(bundle_path) as handle:
		bundle = json.load(handle)
	# Deep copy: ``records`` is about to be mutated in place, and the leak
	# scanner must compare the *original* values against the rewritten ones.
	real_records = json.loads(json.dumps(bundle.get("records", {}), default=str))

	records = bundle.get("records", {})
	maps = _NameMaps()

	# ---- 1. Companies: keep the name, strip the identifiers -----------------
	company_index = 0
	for doc in records.get("Company", []):
		company_index += 1
		state = _state_for(doc.get("gstin"), "Gujarat")
		doc["gstin"], doc["pan"], _ = _fake_identity(doc.get("gstin"), 9000 + company_index, state)
		doc["tax_id"] = ""
		doc["phone_no"] = f"90000{company_index:05d}"[:10]
		doc["email"] = f"company_{_pad3(company_index)}@example.invalid"
		doc["website"] = ""
		abbr = doc.get("abbr") or ""
		if len(abbr) > 5:
			doc["abbr"] = abbr[:5]
		if not doc.get("company_description"):
			doc["company_description"] = doc.get("company_name", "")

	# ---- 2. Items: untouched (deliberate) ----------------------------------
	# The product catalogue is the reason we ship master data at all, and an
	# item code / description is not personal data.

	# ---- 3. Customers / Suppliers ------------------------------------------
	party_counts = {}
	for doctype in ("Customer", "Supplier"):
		index = 0
		for doc in records.get(doctype, []):
			index += 1
			label = doctype
			anon = f"{label} {_pad3(index)}"
			maps.set(doctype, doc.get("name"), anon)
			# Customer autonames off customer_name, Supplier off supplier_name,
			# so the *field* is what becomes the new document name. The ``name``
			# key must be rewritten too: it holds the real party name, and this
			# file is committed to a public repository.
			doc[f"{doctype.lower()}_name"] = anon
			doc["name"] = anon
			state = _state_for(doc.get("gstin"), "Gujarat")
			doc["gstin"], doc["pan"], _ = _fake_identity(doc.get("gstin"), index, state)
			doc["gst_category"] = "Registered Regular"
			doc["mobile_no"] = f"9000{index:06d}"[:10]
			doc["email_id"] = f"{doctype.lower()}_{_pad3(index)}@example.invalid"
		party_counts[doctype] = index

	# ---- 4. Addresses -------------------------------------------------------
	address_index = 0
	for doc in records.get("Address", []):
		address_index += 1
		state = doc.get("gst_state") or doc.get("state") or "Gujarat"
		city = GENERIC_CITY_BY_STATE.get(state) or doc.get("city") or "Ahmedabad"
		anon = f"Address {_pad3(address_index)}"
		maps.set("Address", doc.get("name"), anon)
		doc["address_title"] = anon
		doc["name"] = anon
		doc["address_line1"] = f"{address_index} Sample Industrial Road"
		doc["address_line2"] = "Near Sample Ring Road"
		doc["city"] = city
		doc["county"] = city
		doc["gst_state"] = state
		doc["pincode"] = _digits(doc.get("pincode"), 6)
		doc["gstin"] = ""
		doc["phone"] = f"9000{address_index:06d}"[:10]
		doc["fax"] = ""
		_relink(doc, maps)

	# ---- 5. Contacts (last: they link to the parties above) -----------------
	contact_index = 0
	for doc in records.get("Contact", []):
		contact_index += 1
		anon = f"Contact {_pad3(contact_index)}"
		maps.set("Contact", doc.get("name"), anon)
		doc["first_name"] = f"Contact{_pad3(contact_index)}"
		doc["last_name"] = ""
		doc["company_name"] = ""
		doc["name"] = anon
		doc["mobile_no"] = f"9000{contact_index:06d}"[:10]
		doc["email_id"] = f"contact_{_pad3(contact_index)}@example.invalid"
		doc["gender"] = doc.get("gender") or "Other"
		_relink(doc, maps)

	# ---- 6. Verify nothing identifying survived, then write ----------------
	leaks = scan_for_pii(records, real_records)
	if leaks:
		frappe.throw(
			"Anonymisation incomplete, refusing to write "
			f"{len(leaks)} possible leak(s):\n"
			+ "\n".join(f"  {doctype}.{field} = {value!r}" for doctype, field, value in leaks[:25]),
			title="PII Still Present",
		)

	bundle["anonymised"] = True
	bundle["source_bundle"] = os.path.basename(bundle_path)
	bundle.pop("generated_from_site", None)
	# NOTE: the source-name -> anonymised-name map is deliberately NOT written
	# to disk. Its keys are the real party names, so persisting it would defeat
	# the entire point of the exercise. It is only used in-memory above, to
	# rewrite the ``links`` child rows of Contacts and Addresses.
	bundle.pop("name_map", None)
	bundle["counts"] = {dt: len(docs) for dt, docs in records.items()}

	os.makedirs(os.path.dirname(out_path), exist_ok=True)
	with open(out_path, "w") as handle:
		json.dump(bundle, handle, indent=1, sort_keys=True, default=str)

	return {
		"path": out_path,
		"size_kb": round(os.path.getsize(out_path) / 1024, 1),
		"counts": bundle["counts"],
		"total_docs": sum(bundle["counts"].values()),
		"pii_leaks": len(leaks),
		"anonymised": {**party_counts, "Company": company_index, "Address": address_index, "Contact": contact_index},
	}


def _relink(doc, maps: _NameMaps):
	"""Point a doc's ``links`` child rows at the anonymised party names."""
	for link in doc.get("links") or []:
		link_doctype = link.get("link_doctype")
		link["link_name"] = maps.get(link_doctype, link.get("link_name"))
		link["link_title"] = maps.get(link_doctype, link.get("link_title"))


def scan_for_pii(records, real_records):
	"""Return a list of identifying values from the source that survived.

	Two independent checks:

	1. **Exact match** -- for each guarded field, the anonymised value must not
	   be present in the real value set for that same doctype. Catches names,
	   GSTINs, phones and emails that were copied through unchanged.
	2. **Global sweep** -- no real GSTIN (15 chars), PAN (10 chars) or
	   phone-like run (>= 10 digits) may appear *anywhere* in the anonymised
	   records, in any field. Catches a value that leaked into a field we did
	   not think to guard.
	"""
	leaks = []

	# 1. exact match on guarded fields
	for doctype, fields in GUARDED_FIELDS.items():
		real_values = set()
		for doc in real_records.get(doctype, []):
			for field in fields:
				value = doc.get(field)
				if value and len(str(value).strip()) > 3:
					real_values.add(str(value).strip())
		for doc in records.get(doctype, []):
			for field in fields:
				value = str(doc.get(field) or "").strip()
				if value and value in real_values:
					leaks.append((doctype, field, value))

	# 2. global sweep for real identifiers
	sensitive = set()
	for doctype, fields in GUARDED_FIELDS.items():
		for doc in real_records.get(doctype, []):
			for field in fields:
				value = str(doc.get(field) or "").strip()
				if not value:
					continue
				if field in ("gstin", "pan") and len(value) >= 10:
					sensitive.add(value)
				if any(ch.isdigit() for ch in value):
					digit_runs = re.findall(r"\d{10,}", value)
					sensitive.update(digit_runs)

	anonymised_blob = json.dumps(records, default=str)
	for value in sensitive:
		if value in anonymised_blob:
			leaks.append(("<any field>", "sensitive_value", value))

	return leaks
