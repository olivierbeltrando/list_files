#!/usr/bin/env python3
import logging
import platform
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import list_files
from network_storage import Settings, mount_storage
from local_storage import default_disk, discover_disks, disk_label, mount_disk
from storage_settings import StorageSettings

logger = logging.getLogger(__name__)


class ListFilesApp(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=15)
        self.settings = Settings()
        self.config, self.secrets = {'networkStorages': []}, {}
        try:
            self.config, self.secrets = self.settings.load()
        except (OSError, ValueError) as error:
            messagebox.showerror('Cannot load settings', str(error), parent=master)
        self.search_name = tk.StringVar()
        self.directory = tk.StringVar()
        self.network_directory = tk.StringVar()
        self.disk = tk.StringVar()
        self.disks = [default_disk()]
        self.local_root = Path(self.disks[0]['mountpoint'])
        self.local_initial = self.disks[0]['initial']
        self.mode = tk.StringVar(value='local')
        self.share = tk.StringVar()
        self.status = tk.StringVar(value='Select a directory')
        self.simple_search = tk.BooleanVar(value=True)
        self.result_location = tk.IntVar(value=1)
        self.mounted_path = None
        self.busy = False
        self.completed = queue.Queue()
        self.create_widgets()
        self.pack(fill='both', expand=True)
        master.bind('<Return>', self.process)
        self.after(100, self.poll)
        self.refresh_sources()
        self.after(0, self.refresh_disks)

    def create_widgets(self):
        self.columnconfigure(1, weight=1)
        ttk.Label(self, text='Location label:').grid(row=0, column=0, sticky='w')
        ttk.Entry(self, textvariable=self.search_name).grid(row=0, column=1, columnspan=2, sticky='ew', pady=5)
        modes = ttk.Frame(self)
        modes.grid(row=1, column=0, columnspan=3, sticky='ew')
        for value in ('local', 'network'):
            button = ttk.Radiobutton(modes, text=value.title(), variable=self.mode,
                                     value=value, command=self.change_mode)
            button.pack(side='left', padx=5)
            if value == 'network' and platform.system() != 'Linux':
                button.configure(state='disabled')
        self.settings_button = ttk.Button(modes, text='Shares / credentials…', command=self.edit_settings)
        self.settings_button.pack(side='right')
        self.local_frame = ttk.Frame(self)
        self.local_frame.grid(row=2, column=0, columnspan=3, sticky='ew', pady=8)
        self.local_frame.columnconfigure(0, weight=1)
        self.disk_selector = ttk.Combobox(self.local_frame, textvariable=self.disk,
                                          state='readonly', values=[disk_label(self.disks[0])])
        self.disk_selector.grid(row=0, column=0, sticky='ew')
        self.disk_selector.current(0)
        self.disk_selector.bind('<<ComboboxSelected>>', self.select_disk)
        self.local_mount_button = ttk.Button(self.local_frame, text='Mount', command=self.mount_local)
        self.local_mount_button.grid(row=0, column=1, padx=5)
        self.disk_refresh_button = ttk.Button(self.local_frame, text='Refresh disks', command=self.refresh_disks)
        self.disk_refresh_button.grid(row=0, column=2, padx=5)
        ttk.Entry(self.local_frame, textvariable=self.directory, state='readonly').grid(
            row=1, column=0, sticky='ew', pady=(5, 0))
        self.local_browse_button = ttk.Button(self.local_frame, text='Browse…', command=self.select_directory)
        self.local_browse_button.grid(row=1, column=1, padx=5, pady=(5, 0))
        self.network_frame = ttk.Frame(self)
        self.network_frame.grid(row=2, column=0, columnspan=3, sticky='ew', pady=8)
        self.network_frame.columnconfigure(0, weight=1)
        self.share_selector = ttk.Combobox(self.network_frame, textvariable=self.share, state='readonly')
        self.share_selector.grid(row=0, column=0, sticky='ew')
        self.share_selector.bind('<<ComboboxSelected>>', self.invalidate)
        self.mount_button = ttk.Button(self.network_frame, text='Mount', command=self.mount)
        self.mount_button.grid(row=0, column=1, padx=5)
        ttk.Entry(self.network_frame, textvariable=self.network_directory,
                  state='readonly').grid(row=1, column=0, sticky='ew', pady=(5, 0))
        self.network_browse_button = ttk.Button(self.network_frame, text='Browse…',
                                                command=self.select_network_directory)
        self.network_browse_button.grid(row=1, column=1, padx=5, pady=(5, 0))
        options = ttk.LabelFrame(self, text='Search options', padding=10)
        options.grid(row=3, column=0, columnspan=3, sticky='ew', pady=5)
        ttk.Checkbutton(options, text='Only search the selected folder (not subfolders)', variable=self.simple_search).pack(anchor='w')
        output = ttk.LabelFrame(self, text='Output location', padding=10)
        output.grid(row=4, column=0, columnspan=3, sticky='ew', pady=5)
        for value, label in [(1, 'Store result.csv in my home directory'), (2, 'Store result.csv in the selected directory')]:
            ttk.Radiobutton(output, text=label, variable=self.result_location, value=value).pack(anchor='w')
        actions = ttk.Frame(self)
        actions.grid(row=5, column=0, columnspan=3, pady=10)
        self.run_button = ttk.Button(actions, text='Find / generate file list', command=self.process)
        self.run_button.pack(side='left', padx=5)
        ttk.Label(self, textvariable=self.status, wraplength=650).grid(row=6, column=0, columnspan=3, sticky='w')

    def refresh_sources(self):
        self.share_selector['values'] = [f"{s['server']}/{s['folder']} ({s['networkName']})" for s in self.config['networkStorages']]
        if self.config['networkStorages']:
            self.share_selector.current(0)
        else:
            self.share.set('')
        self.change_mode()

    def current_storage(self):
        index = self.share_selector.current()
        return self.config['networkStorages'][index] if index >= 0 else None

    def invalidate(self, event=None):
        self.mounted_path = None
        self.network_directory.set('')
        self.update_buttons()
        self.status.set('Click Mount before finding files')

    def change_mode(self):
        if self.busy:
            self.mode.set(self.active_mode)
            return
        self.local_frame.grid_remove()
        self.network_frame.grid_remove()
        (self.local_frame if self.mode.get() == 'local' else self.network_frame).grid()
        self.invalidate()
        if self.mode.get() == 'local':
            self.status.set('Ready' if self.directory.get() else 'Select a directory')

    def update_buttons(self):
        ready = (self.local_root is not None and bool(self.directory.get())) if self.mode.get() == 'local' else self.mounted_path is not None
        self.run_button.configure(state='normal' if ready and not self.busy else 'disabled')
        self.mount_button.configure(state='normal' if self.current_storage() and not self.busy else 'disabled')
        self.network_browse_button.configure(
            state='normal' if self.mounted_path is not None and not self.busy else 'disabled')
        self.share_selector.configure(state='disabled' if self.busy else 'readonly')
        self.settings_button.configure(state='disabled' if self.busy else 'normal')
        self.disk_selector.configure(state='disabled' if self.busy else 'readonly')
        self.disk_refresh_button.configure(state='disabled' if self.busy else 'normal')
        self.local_mount_button.configure(
            text='Mounted' if self.local_root is not None else 'Mount',
            state='normal' if self.local_root is None and self.current_disk() and not self.busy else 'disabled')
        self.local_browse_button.configure(
            state='normal' if self.local_root is not None and not self.busy else 'disabled')

    def edit_settings(self):
        if not self.busy:
            StorageSettings(self.master, self.settings, self.config, self.secrets, self.settings_saved)

    def settings_saved(self, config, secrets):
        self.config, self.secrets = config, secrets
        self.refresh_sources()

    def current_disk(self):
        index = self.disk_selector.current()
        return self.disks[index] if 0 <= index < len(self.disks) else None

    def select_disk(self, event=None):
        if self.busy:
            return
        disk = self.current_disk()
        mountpoint = disk['mountpoint'] if disk else None
        self.local_root = Path(mountpoint) if mountpoint else None
        self.local_initial = disk['initial'] if disk else None
        self.directory.set(mountpoint if disk and disk['device'] is not None and mountpoint else '')
        self.update_buttons()
        self.status.set('Choose a folder with Browse' if self.local_root is not None else 'Click Mount before browsing this disk')

    def refresh_disks(self):
        if self.busy:
            return
        selected = self.current_disk()
        old_device = selected['device'] if selected else None
        old_root, old_directory = self.local_root, self.directory.get()
        def refreshed(disks):
            self.disks = disks
            self.disk_selector['values'] = [disk_label(disk) for disk in disks]
            index = next((i for i, disk in enumerate(disks) if disk['device'] == old_device), 0)
            self.disk_selector.current(index)
            self.select_disk()
            if (disks[index]['device'] == old_device and self.local_root == old_root
                    and old_directory and Path(old_directory).is_dir()):
                self.directory.set(old_directory)
            self.update_buttons()
            self.status.set('Disk list refreshed')
        self.start(discover_disks, refreshed, 'Looking for disks…')

    def mount_local(self):
        disk = self.current_disk()
        if self.busy or not disk:
            return
        def mounted(path):
            self.local_root = path
            self.local_initial = disk['initial'] if disk['device'] is None else str(path)
            disk['mountpoint'] = str(path)
            disk['initial'] = self.local_initial
            self.directory.set('' if disk['device'] is None else str(path))
            index = self.disk_selector.current()
            self.disk_selector['values'] = [disk_label(entry) for entry in self.disks]
            self.disk_selector.current(index)
            self.status.set(f'Mounted: {path}')
        self.start(lambda: mount_disk(disk), mounted, 'Mounting disk…')

    def select_directory(self):
        if self.busy or self.local_root is None:
            return
        selected = filedialog.askdirectory(
            parent=self.master, title='Select a directory to analyse',
            initialdir=self.directory.get() or self.local_initial or str(self.local_root),
            mustexist=True)
        if not selected:
            return
        try:
            directory = Path(selected).resolve()
            directory.relative_to(self.local_root.resolve())
            if not directory.is_dir():
                raise ValueError('Selected folder is unavailable')
        except (OSError, ValueError) as error:
            logger.warning('Cannot select local folder %s: %s', selected, error)
            self.status.set('Please choose an existing folder inside the selected disk')
            return
        self.directory.set(str(directory))
        self.update_buttons()
        self.status.set('Ready')

    def select_network_directory(self):
        if self.busy or self.mounted_path is None:
            return
        selected = filedialog.askdirectory(
            parent=self.master, title='Select a NAS subfolder to analyse',
            initialdir=self.network_directory.get() or str(self.mounted_path),
            mustexist=True)
        if not selected:
            return
        try:
            relative = Path(selected).resolve().relative_to(self.mounted_path.resolve())
            directory = self.mounted_path / relative
            if not directory.is_dir():
                raise ValueError('Selected folder is unavailable')
        except (OSError, ValueError) as error:
            logger.warning('Cannot select NAS folder %s: %s', selected, error)
            self.status.set('Please choose an existing folder inside the mounted NAS folder')
            return
        self.network_directory.set(str(directory))
        self.update_buttons()
        self.status.set(f'Ready: {directory}')

    def start(self, job, on_success, status):
        if self.busy:
            return
        self.active_mode = self.mode.get()
        self.busy = True
        self.status.set(status)
        self.update_buttons()
        def run():
            try:
                self.completed.put((on_success, job(), None))
            except Exception as error:
                logger.exception('Operation failed')
                self.completed.put((on_success, None, error))
        threading.Thread(target=run, daemon=True).start()

    def poll(self):
        try:
            callback, value, error = self.completed.get_nowait()
        except queue.Empty:
            pass
        else:
            self.busy = False
            if error:
                self.status.set(f'Error: {error}')
            else:
                callback(value)
            self.update_buttons()
        self.after(100, self.poll)

    def mount(self):
        storage = self.current_storage()
        if self.busy or not storage:
            return
        self.invalidate()
        def mounted(path):
            self.mounted_path = path
            self.network_directory.set(str(path))
            self.status.set(f'Mounted: {path}')
        self.start(lambda: mount_storage(storage, self.secrets[storage['credName']]), mounted, 'Mounting…')

    def get_output_path(self, source_directory):
        return (Path.home() if self.result_location.get() == 1 else source_directory) / 'result.csv'

    def process(self, event=None):
        if self.busy:
            return
        network = self.mode.get() == 'network'
        if network:
            source = (Path(self.network_directory.get()) if self.network_directory.get()
                      else self.mounted_path) if self.mounted_path is not None else None
        else:
            source = Path(self.directory.get()) if self.local_root is not None and self.directory.get() else None
        if source is None:
            self.status.set('Click Mount first' if network or self.local_root is None else 'Select a directory')
            return
        if not source.is_dir():
            if network:
                self.invalidate()
            else:
                self.directory.set('')
                self.local_root = None
                self.update_buttons()
            self.status.set('Source is unavailable; select it or mount it again')
            return
        self.update_buttons()
        output = self.get_output_path(source)
        label, simple = self.search_name.get(), self.simple_search.get()
        prefix = None
        if network:
            prefix = str(Path(self.current_storage()['folder'].strip('/'))
                         / source.relative_to(self.mounted_path))
        def job():
            skipped = []
            files = list_files.find_files(str(source), label, _simpleSearch=simple,
                                         _on_error=skipped.append)
            # Export portable paths in network mode.
            exported = list_files.with_path_prefix(files, source, prefix) if network else files
            list_files.write_cvs(exported, output)
            return files, skipped
        def found(result):
            files, skipped = result
            status = f'{len(files)} files written to {output}'
            if skipped:
                status += f'; WARNING: {len(skipped)} inaccessible paths skipped (see logs)'
            self.status.set(status)
        self.start(job, found, 'Searching…')


def main():
    root = tk.Tk()
    root.title('Generate file list')
    root.minsize(650, 380)
    ListFilesApp(root)
    try:
        root.mainloop()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
