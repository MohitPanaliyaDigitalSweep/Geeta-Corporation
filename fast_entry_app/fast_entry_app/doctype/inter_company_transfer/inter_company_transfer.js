frappe.ui.form.on('Inter Company Transfer', {
	setup(frm) {
		frm.set_query('company', function() {
			return {
				filters: {
					name: ['!=', frm.doc.to_company]
				}
			};
		});
		frm.set_query('to_company', function() {
			return {
				filters: {
					name: ['!=', frm.doc.company]
				}
			};
		});
		frm.set_query('from_account', function() {
			return {
				filters: {
					company: frm.doc.company,
					is_group: 0
				}
			};
		});
		frm.set_query('to_account', function() {
			return {
				filters: {
					company: frm.doc.to_company,
					is_group: 0
				}
			};
		});
	},

	refresh(frm) {
		frm.trigger('set_warehouse_queries');

		if (frm.doc.docstatus === 1 && frm.doc.status === 'Transfer Created') {
			frm.add_custom_button(__('View All Documents'), function() {
				frm.trigger('show_generated_documents');
			}, __('Actions'));
			frm.add_custom_button(__('Create Payment Entries'), function() {
				frm.trigger('create_payment_entries');
			}, __('Actions'));
			frm.page.set_indicator(__('Transfer Created'), 'green');
		} else if (frm.doc.docstatus === 1 && frm.doc.status === 'Submitted') {
			frm.page.set_indicator(__('Processing...'), 'orange');
		} else if (frm.doc.docstatus === 0) {
			frm.page.set_indicator(__('Draft'), 'gray');
		}
	},

	company(frm) {
		frm.set_query('to_company', function() {
			return {
				filters: {
					name: ['!=', frm.doc.company]
				}
			};
		});
		frm.trigger('set_warehouse_queries');
		frm.trigger('set_defaults');
		if (frm.doc.items) {
			frm.doc.items.forEach(row => {
				row.source_warehouse = '';
			});
			frm.refresh_field('items');
		}
	},

	to_company(frm) {
		frm.set_query('company', function() {
			return {
				filters: {
					name: ['!=', frm.doc.to_company]
				}
			};
		});
		frm.trigger('set_warehouse_queries');
		if (frm.doc.items) {
			frm.doc.items.forEach(row => {
				row.target_warehouse = '';
			});
			frm.refresh_field('items');
		}
	},

	set_defaults(frm) {
		if (frm.doc.company && !frm.doc.transaction_type) {
			frm.set_value('transaction_type', 'Inter Company Stock Transfer');
		}
		if (frm.doc.company && !frm.doc.posting_date) {
			frm.set_value('posting_date', frappe.datetime.get_today());
		}
	},

	set_warehouse_queries(frm) {
		if (frm.doc.company) {
			frm.set_query('source_warehouse', 'items', function() {
				return {
					filters: {
						company: frm.doc.company,
						is_group: 0
					}
				};
			});
		}
		if (frm.doc.to_company) {
			frm.set_query('target_warehouse', 'items', function() {
				return {
					filters: {
						company: frm.doc.to_company,
						is_group: 0
					}
				};
			});
		}
	},

	create_payment_entries(frm) {
		const d = new frappe.ui.Dialog({
			title: __('Create Payment Entries'),
			fields: [
				{
					label: __('Posting Date'),
					fieldname: 'posting_date',
					fieldtype: 'Date',
					default: frappe.datetime.get_today(),
					reqd: 1
				}
			],
			primary_action_label: __('Create'),
			primary_action(values) {
				d.hide();
				frappe.call({
					method: 'fast_entry_app.api.ict.create_payment_entries_for_ict',
					args: {
						ict_name: frm.doc.name,
						posting_date: values.posting_date
					},
					callback(r) {
						if (r.message && r.message.created && r.message.created.length) {
							frappe.msgprint(__('Payment Entries created: {0}', [r.message.created.join(', ')]));
							frm.reload_doc();
						} else {
							frappe.msgprint(__('No payment entries were created. Outstanding may already be settled.'));
						}
					}
				});
			}
		});
		d.show();
	},

	show_generated_documents(frm) {
		if (!frm.doc.generated_documents || frm.doc.generated_documents.length === 0) {
			frappe.msgprint(__('No generated documents found'));
			return;
		}

		let html = '<table class="table table-bordered" style="font-size:13px;">';
		html += '<thead><tr><th>#</th><th>Document Type</th><th>Document Name</th><th>Company</th><th>Date</th><th>Amount</th><th>Status</th></tr></thead><tbody>';

		let idx = 1;
		frm.doc.generated_documents.forEach(function(row) {
			let route = '/app/' + row.document_type.replace(/ /g, '-').toLowerCase() + '/' + row.document_name;
			html += '<tr>';
			html += '<td>' + idx + '</td>';
			html += '<td>' + row.document_type + '</td>';
			html += '<td><a href="' + route + '" target="_blank"><b>' + row.document_name + '</b></a></td>';
			html += '<td>' + (row.company || '') + '</td>';
			html += '<td>' + (row.posting_date || '') + '</td>';
			html += '<td>' + format_currency(row.grand_total) + '</td>';
			html += '<td><span class="indicator-pill ' + (row.status === 'Submitted' ? 'green' : row.status === 'Cancelled' ? 'red' : 'orange') + '">' + (row.status || '') + '</span></td>';
			html += '</tr>';
			idx++;
		});

		html += '</tbody></table>';

		frappe.msgprint({
			title: __('Generated Documents ({0})', [frm.doc.generated_documents.length]),
			indicator: 'green',
			message: html
		});
	}
});

frappe.ui.form.on('Inter Company Transfer Item', {
	item_code: function(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		if (row.item_code) {
			frappe.call({
				method: 'frappe.client.get_value',
				args: {
					doctype: 'Item',
					filters: { name: row.item_code },
					fieldname: ['stock_uom', 'item_name']
				},
				callback: function(r) {
					if (r.message) {
						frappe.model.set_value(cdt, cdn, 'stock_uom', r.message.stock_uom);
						frappe.model.set_value(cdt, cdn, 'item_name', r.message.item_name);
						if (!row.uom) {
							frappe.model.set_value(cdt, cdn, 'uom', r.message.stock_uom);
						}
					}
				}
			});
		}
	},

	qty: function(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		frappe.model.set_value(cdt, cdn, 'amount', (row.qty || 0) * (row.rate || 0));
	},

	rate: function(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		frappe.model.set_value(cdt, cdn, 'amount', (row.qty || 0) * (row.rate || 0));
	}
});
