import frappe

def get_context(context):
    context.title = "Party Group Details"
    context.no_cache = 1
    context.include_custom = 1
