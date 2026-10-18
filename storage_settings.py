"""Tk settings editor for named credentials and SMB shares."""
import copy
import tkinter as tk
from tkinter import messagebox, ttk
from network_storage import validate_settings


class StorageSettings(tk.Toplevel):
    def __init__(self, parent, settings, config, secrets, on_save):
        super().__init__(parent)
        self.title('Credentials and NAS shares')
        self.transient(parent)
        self.grab_set()
        self.settings = settings
        self.config = copy.deepcopy(config)
        self.secrets = copy.deepcopy(secrets)
        self.on_save = on_save
        self.selected = {'Shares': None, 'Credentials': None}
        self.forms = {}
        notebook = ttk.Notebook(self)
        notebook.pack(fill='both', expand=True, padx=12, pady=12)
        for kind, fields in [('Credentials', ['name', 'user', 'password']),
                             ('Shares', ['server', 'folder', 'credName', 'networkName'])]:
            tab = ttk.Frame(notebook, padding=10)
            notebook.add(tab, text=kind)
            listing = tk.Listbox(tab, exportselection=False, width=55, height=6)
            listing.grid(row=0, column=0, columnspan=2, sticky='ew')
            variables = {}
            for row, field in enumerate(fields, 1):
                ttk.Label(tab, text=field).grid(row=row, column=0, sticky='w', pady=3)
                variable = tk.StringVar(value='WORKGROUP' if field == 'networkName' else '')
                variables[field] = variable
                if kind == 'Shares' and field == 'credName':
                    self.credential_picker = ttk.Combobox(tab, textvariable=variable,
                                                        state='readonly')
                    self.credential_picker.grid(row=row, column=1, sticky='ew')
                else:
                    ttk.Entry(tab, textvariable=variable, show='*' if field == 'password' else '').grid(row=row, column=1, sticky='ew')
            buttons = ttk.Frame(tab)
            buttons.grid(row=len(fields) + 1, column=0, columnspan=2, pady=8)
            for label, action in [('New', self.clear), ('Apply entry', self.apply), ('Delete', self.delete)]:
                ttk.Button(buttons, text=label, command=lambda k=kind, a=action: a(k)).pack(side='left', padx=3)
            self.forms[kind] = (listing, variables)
            listing.bind('<<ListboxSelect>>', lambda event, k=kind: self.select(k))
            tab.columnconfigure(1, weight=1)
        ttk.Label(self, text='Apply each entry before saving. Passwords are stored locally in secrets.json.').pack(padx=12)
        actions = ttk.Frame(self)
        actions.pack(pady=12)
        ttk.Button(actions, text='Save settings', command=self.save).pack(side='left', padx=5)
        ttk.Button(actions, text='Cancel', command=self.destroy).pack(side='left', padx=5)
        self.refresh()

    def refresh_credentials(self):
        names = list(self.secrets)
        self.credential_picker['values'] = names
        variable = self.forms['Shares'][1]['credName']
        if variable.get() not in names:
            variable.set(names[0] if names else '')

    def refresh(self):
        self.refresh_credentials()
        for kind, (listing, _) in self.forms.items():
            listing.delete(0, 'end')
            if kind == 'Credentials':
                for name in self.secrets:
                    listing.insert('end', name)
            else:
                for share in self.config['networkStorages']:
                    listing.insert('end', f"{share['server']}/{share['folder']} ({share['credName']})")

    def clear(self, kind):
        self.selected[kind] = None
        listing, variables = self.forms[kind]
        listing.selection_clear(0, 'end')
        for field, variable in variables.items():
            variable.set('WORKGROUP' if field == 'networkName' else '')
        if kind == 'Shares':
            self.refresh_credentials()

    def select(self, kind):
        listing, variables = self.forms[kind]
        if not listing.curselection():
            return
        index = listing.curselection()[0]
        if kind == 'Credentials':
            key = list(self.secrets)[index]
            values = dict(self.secrets[key], name=key)
        else:
            key = index
            values = self.config['networkStorages'][index]
        self.selected[kind] = key
        for field, variable in variables.items():
            variable.set(values.get(field, 'WORKGROUP' if field == 'networkName' else ''))

    def apply(self, kind):
        values = {field: var.get() for field, var in self.forms[kind][1].items()}
        config, secrets = copy.deepcopy(self.config), copy.deepcopy(self.secrets)
        selected = self.selected[kind]
        if kind == 'Credentials':
            name = values.pop('name').strip()
            if name in secrets and name != selected:
                messagebox.showerror('Settings', 'Credential name already exists', parent=self)
                return
            if selected is not None and selected != name:
                del secrets[selected]
                for share in config['networkStorages']:
                    if share['credName'] == selected:
                        share['credName'] = name
            secrets[name] = values
        else:
            values = {key: value.strip() for key, value in values.items()}
            values['networkName'] = values['networkName'] or 'WORKGROUP'
            values['type'] = 'smb'
            if selected is None:
                config['networkStorages'].append(values)
            else:
                config['networkStorages'][selected] = values
        try:
            validate_settings(config, secrets)
        except ValueError as error:
            messagebox.showerror('Settings', str(error), parent=self)
            return
        self.config, self.secrets = config, secrets
        if kind == 'Credentials' and selected is not None and selected != name:
            variable = self.forms['Shares'][1]['credName']
            if variable.get() == selected:
                variable.set(name)
        self.clear(kind)
        self.refresh()

    def delete(self, kind):
        selected = self.selected[kind]
        if selected is None:
            return
        if kind == 'Credentials':
            if any(s['credName'] == selected for s in self.config['networkStorages']):
                messagebox.showerror('Settings', 'Delete or update shares using this credential first', parent=self)
                return
            del self.secrets[selected]
        else:
            del self.config['networkStorages'][selected]
        self.clear(kind)
        self.refresh()

    def save(self):
        try:
            self.settings.save(self.config, self.secrets)
        except (OSError, ValueError) as error:
            messagebox.showerror('Settings', str(error), parent=self)
            return
        self.on_save(self.config, self.secrets)
        self.destroy()
