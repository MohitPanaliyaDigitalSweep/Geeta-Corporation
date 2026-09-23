frappe.pages['fast-party-group'].on_page_load = function(wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'Party Groups',
        single_column: true
    });

    var manager = new PartyGroupManager(page);
    window._party_group_manager = manager;
};

class PartyGroupManager {
    constructor(page) {
        this.page = page;
        this.groups = [];
        this.make();
    }

    make() {
        this.$root = $(this.page.main.empty());
        this.render();
        this.load_groups();
    }

    render() {
        this.$root.html(`
            <div class="party-group-list" style="padding: 15px;">
                <div style="margin-bottom: 15px;">
                    <button class="btn btn-primary btn-sm" id="pg-new-btn">
                        <i class="fa fa-plus"></i> New Group
                    </button>
                </div>
                <div id="pg-list"></div>
            </div>
        `);
        this.$list = this.$root.find('#pg-list');
        this.$root.find('#pg-new-btn').on('click', () => this.show_create());
    }

    load_groups() {
        frappe.call({
            method: 'fast_entry_app.api.party_group.get_party_groups',
            callback: (r) => {
                this.groups = r.message || [];
                this.render_list();
            }
        });
    }

    render_list() {
        if (!this.groups.length) {
            this.$list.html('<p class="text-muted">No groups yet. Create one to get started.</p>');
            return;
        }

        let rows = this.groups.map(g => {
            let type_cls = g.group_type === 'Supplier' ? 'warning' : (g.group_type === 'Customer' ? 'info' : 'success');
            return `<tr>
                <td><strong>${frappe.utils.escape_html(g.group_name)}</strong></td>
                <td><span class="badge badge-${type_cls}">${g.group_type}</span></td>
                <td>${g.party_count || 0}</td>
                <td>${frappe.utils.escape_html(g.description || '')}</td>
                <td>
                    <button class="btn btn-xs btn-default pg-edit" data-name="${g.name}">
                        <i class="fa fa-edit"></i>
                    </button>
                    <button class="btn btn-xs btn-danger pg-delete" data-name="${g.name}">
                        <i class="fa fa-trash"></i>
                    </button>
                    <button class="btn btn-xs btn-success pg-pay" data-name="${g.name}">
                        <i class="fa fa-money"></i> Pay
                    </button>
                </td>
            </tr>`;
        }).join('');

        this.$list.html(`
            <table class="table table-bordered table-hover" style="font-size: 13px;">
                <thead><tr>
                    <th style="width:30%">Group Name</th>
                    <th style="width:15%">Type</th>
                    <th style="width:10%">Parties</th>
                    <th style="width:25%">Description</th>
                    <th style="width:20%">Actions</th>
                </tr></thead>
                <tbody>${rows}</tbody>
            </table>
        `);

        this.$list.find('.pg-edit').on('click', (e) => {
            this.edit_group($(e.currentTarget).data('name'));
        });
        this.$list.find('.pg-delete').on('click', (e) => {
            this.delete_group($(e.currentTarget).data('name'));
        });
        this.$list.find('.pg-pay').on('click', (e) => {
            frappe.set_route('fast-bulk-payment', { group: $(e.currentTarget).data('name') });
        });
    }

    show_create() {
        this._show_dialog(null);
    }

    edit_group(name) {
        frappe.call({
            method: 'fast_entry_app.api.party_group.get_group_parties',
            args: { group_name: name },
            callback: (r) => {
                var group = this.groups.find(g => g.name === name);
                if (group) {
                    group._parties = r.message || [];
                    this._show_dialog(group);
                }
            }
        });
    }

    _show_dialog(group) {
        var is_edit = !!group;
        var self = this;

        // Determine initial party_type based on group_type
        var group_type = group ? group.group_type : 'Supplier';
        var initial_party_type = (group_type === 'Both') ? 'Supplier' : group_type;

        var d = new frappe.ui.Dialog({
            title: is_edit ? 'Edit: ' + group.group_name : 'New Party Group',
            fields: [
                {
                    fieldname: 'group_name',
                    fieldtype: 'Data',
                    label: 'Group Name',
                    reqd: 1,
                    default: group ? group.group_name : ''
                },
                {
                    fieldname: 'group_type',
                    fieldtype: 'Select',
                    label: 'Group Type',
                    options: 'Supplier\nCustomer\nBoth',
                    reqd: 1,
                    default: group_type
                },
                {
                    fieldname: 'description',
                    fieldtype: 'Small Text',
                    label: 'Description',
                    default: group ? (group.description || '') : ''
                },
                {
                    fieldname: 'section_parties',
                    fieldtype: 'Section Break',
                    label: 'Add Parties'
                },
                {
                    fieldname: 'party_type',
                    fieldtype: 'Select',
                    label: 'Party Type',
                    options: 'Supplier\nCustomer',
                    default: initial_party_type,
                    read_only: (group_type !== 'Both')
                },
                {
                    fieldname: 'party',
                    fieldtype: 'Link',
                    label: 'Party',
                    options: initial_party_type
                },
                {
                    fieldname: 'party_name_display',
                    fieldtype: 'Read Only',
                    label: 'Name',
                    read_only: 1
                },
                {
                    fieldname: 'gstin_display',
                    fieldtype: 'Read Only',
                    label: 'GSTIN',
                    read_only: 1
                },
                {
                    fieldname: 'add_btn',
                    fieldtype: 'Button',
                    label: 'Add to Group'
                },
                {
                    fieldname: 'section_current',
                    fieldtype: 'Section Break',
                    label: 'Current Parties'
                },
                {
                    fieldname: 'current_parties',
                    fieldtype: 'Small Text',
                    label: '',
                    read_only: 1,
                    default: ''
                }
            ],
            primary_action_label: is_edit ? 'Update' : 'Create',
            primary_action: function(values) {
                self._save_from_dialog(d, group);
            }
        });

        d.show();

        // Store current parties list
        var parties_list = [];
        if (is_edit && group._parties) {
            parties_list = group._parties.slice();
        }
        self._update_parties_display(d, parties_list);

        // When group_type changes, auto-set party_type and lock/unlock it
        d.fields_dict.group_type.$wrapper.on('change', 'select', function() {
            var gt = d.get_value('group_type');
            if (gt === 'Both') {
                d.fields_dict.party_type.df.read_only = false;
                d.fields_dict.party_type.set_input('Supplier');
            } else {
                d.fields_dict.party_type.df.read_only = true;
                d.fields_dict.party_type.set_input(gt);
            }
            d.fields_dict.party_type.$wrapper.trigger('change');
            d.fields_dict.party.df.options = d.get_value('party_type');
            d.fields_dict.party.set_input('');
            d.fields_dict.party_name_display.set_input('');
            d.fields_dict.gstin_display.set_input('');
        });

        // Update Link options when party_type changes
        d.fields_dict.party_type.$wrapper.on('change', 'select', function() {
            var type = d.get_value('party_type');
            d.fields_dict.party.df.options = type;
            d.fields_dict.party.set_input('');
            d.fields_dict.party_name_display.set_input('');
            d.fields_dict.gstin_display.set_input('');
        });

        // Auto-fill when party is selected
        d.fields_dict.party.$wrapper.on('change', 'input', function() {
            var party_type = d.get_value('party_type');
            var party = d.get_value('party');
            if (!party_type || !party) return;

            frappe.call({
                method: 'frappe.client.get_value',
                args: {
                    doctype: party_type,
                    filters: { name: party },
                    fieldname: [party_type === 'Supplier' ? 'supplier_name' : 'customer_name', 'gstin']
                },
                callback: function(r) {
                    if (r && r.message) {
                        var name_field = party_type === 'Supplier' ? 'supplier_name' : 'customer_name';
                        d.fields_dict.party_name_display.set_input(r.message[name_field] || '');
                        d.fields_dict.gstin_display.set_input(r.message.gstin || '');
                    }
                }
            });
        });

        // Add button handler
        d.fields_dict.add_btn.$input.on('click', function() {
            var party_type = d.get_value('party_type');
            var party = d.get_value('party');
            var party_name = d.get_value('party_name_display') || '';
            var gstin = d.get_value('gstin_display') || '';

            if (!party) {
                frappe.msgprint('Please select a party');
                return;
            }

            // Check duplicate
            if (parties_list.find(p => p.party_type === party_type && p.party === party)) {
                frappe.msgprint('Party already added');
                return;
            }

            parties_list.push({ party_type, party, party_name, gstin });
            self._update_parties_display(d, parties_list);

            // Clear inputs
            d.fields_dict.party.set_input('');
            d.fields_dict.party_name_display.set_input('');
            d.fields_dict.gstin_display.set_input('');
        });

        // Store reference for saving
        d._parties_list = parties_list;
    }

    _update_parties_display(d, parties_list) {
        var self = this;
        if (!parties_list.length) {
            d.fields_dict.current_parties.set_input('No parties added yet');
            // Remove custom HTML if any
            d.fields_dict.current_parties.$wrapper.find('.pg-parties-html').remove();
            return;
        }
        var html = parties_list.map((p, idx) => {
            return `<div class="pg-party-row" data-idx="${idx}" style="display:flex;align-items:center;justify-content:space-between;padding:4px 8px;border-bottom:1px solid #eee;">
                <span><b>${p.party_type}</b>: ${frappe.utils.escape_html(p.party)} (${frappe.utils.escape_html(p.party_name || '')})</span>
                <button class="btn btn-xs btn-danger pg-remove-party" data-idx="${idx}" style="margin-left:8px;"><i class="fa fa-times"></i></button>
            </div>`;
        }).join('');
        d.fields_dict.current_parties.set_input(parties_list.length + ' party(ies) in group');
        var $wrapper = d.fields_dict.current_parties.$wrapper;
        $wrapper.find('.pg-parties-html').remove();
        $wrapper.append(`<div class="pg-parties-html" style="max-height:150px;overflow-y:auto;border:1px solid #d1d8dd;border-radius:4px;margin-top:4px;">${html}</div>`);
        $wrapper.find('.pg-remove-party').on('click', function() {
            var idx = parseInt($(this).data('idx'));
            parties_list.splice(idx, 1);
            d._parties_list = parties_list;
            self._update_parties_display(d, parties_list);
        });
    }

    _save_from_dialog(d, group) {
        var parties_list = d._parties_list || [];
        var values = {
            group_name: d.get_value('group_name'),
            group_type: d.get_value('group_type'),
            description: d.get_value('description'),
            parties: parties_list,
            existing_name: group ? group.name : ''
        };

        frappe.call({
            method: 'fast_entry_app.api.party_group.create_party_group',
            args: { data: JSON.stringify(values) },
            freeze: true,
            freeze_message: 'Saving...',
            callback: (r) => {
                if (r.message) {
                    frappe.show_alert({message: 'Group saved', indicator: 'green'});
                    d.hide();
                    this.load_groups();
                }
            }
        });
    }

    delete_group(name) {
        var self = this;
        frappe.confirm('Delete this group? Parties will be unlinked.', function() {
            frappe.call({
                method: 'fast_entry_app.api.party_group.delete_party_group',
                args: { name: name },
                freeze: true,
                callback: function() {
                    frappe.show_alert({message: 'Group deleted', indicator: 'green'});
                    self.load_groups();
                }
            });
        });
    }
}
