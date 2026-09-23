import frappe

no_cache = True


def get_context(context):
    context.no_breadcrumbs = True
    context.no_header = True
    context.title = "Fast Ledger & P&L"