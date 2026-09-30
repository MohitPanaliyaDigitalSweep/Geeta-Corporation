"""Repair sites where Fast Entry App was installed before ERPNext.

Installing this app on a site that did not yet have ERPNext silently created
none of our custom fields: Frappe skips fixture syncing for DocTypes that do
not exist, and the old item-table patch could not insert against a missing
table either. The site looked fine, but the raw ``SUM(fe_box)`` queries in
``api/stock_report.py``/``api/reports.py``/``api/ict.py``/``api/quotation.py``
then failed with "Unknown column", and invoice lines silently lost their
Box/PCS/LTR values because ``get_valid_dict`` drops unknown keys.

Running the shared definition ensures everything is created on a site that has
since gained ERPNext. It is idempotent, so re-running is harmless.
"""

from fast_entry_app.setup_custom_fields import execute

execute()
