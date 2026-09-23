// Fast Entry App - Global JS
// This file is loaded on every desk page

frappe.provide("fast_entry_app");
fast_entry_app.version = "0.0.1";

// Fix Frappe v16 checkbox: prevent sliding by keeping border on check
$(function() {
    $("<style>" +
        "input[type='checkbox']:checked{" +
        "border:1px solid var(--primary)!important;" +
        "}" +
    "</style>").appendTo("head");
});
