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

// Prevent accidental value changes on number inputs:
// - mouse-wheel over (or while) a focused number input steps the value in Chrome/Edge
// - ArrowUp/ArrowDown keys step the value while typing
// Both are annoying on dense entry forms, so neutralize them globally.
// Uses capture-phase vanilla listeners so dynamically added rows are covered too.
(function() {
    function is_number_input(el) {
        return !!(el && el.tagName === "INPUT" && el.type === "number");
    }
    // Wheel: a wheel step only lands on a number input while it has focus, so
    // drop focus first (page keeps scrolling normally, value untouched).
    // No preventDefault: blocking it would freeze page scroll over inputs.
    document.addEventListener("wheel", function(e) {
        if (is_number_input(e.target)) {
            e.target.blur();
        } else if (is_number_input(document.activeElement)) {
            document.activeElement.blur();
        }
    }, { passive: true, capture: true });
    // Arrow keys: stop Up/Down from stepping number inputs. Left/Right/Home/End
    // and all other keys still work, so editing/typing is unaffected.
    document.addEventListener("keydown", function(e) {
        if ((e.key === "ArrowUp" || e.key === "ArrowDown") && is_number_input(e.target)) {
            e.preventDefault();
        }
    }, true);
})();
