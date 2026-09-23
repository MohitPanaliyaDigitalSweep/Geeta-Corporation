import frappe

def get_context(context):
    context.title = "Sales Person Detailed Report"
    context.no_cache = 1
    context.include_custom = 1
