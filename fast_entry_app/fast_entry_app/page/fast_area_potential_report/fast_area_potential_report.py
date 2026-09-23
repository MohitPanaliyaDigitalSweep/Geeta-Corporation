import frappe

def get_context(context):
    context.title = "Area Wise Product Potential"
    context.no_cache = 1
    context.include_custom = 1
