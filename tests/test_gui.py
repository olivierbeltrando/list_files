"""Headless checks for the source/mount state gates, including Return shortcuts."""
import csv
import unittest
from unittest.mock import MagicMock, Mock, patch
from pathlib import Path
import tempfile

from gui import ListFilesApp


class Value:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class GuiStateTests(unittest.TestCase):
    def app(self, mode):
        app = object.__new__(ListFilesApp)
        app.mode = Value(mode)
        app.directory = Value('')
        app.network_directory = Value('')
        app.disk = Value('')
        app.disks = [dict(device=None, label='Default filesystem', mountpoint='/', initial=str(Path.home()), size='')]
        app.local_root = Path('/')
        app.local_initial = str(Path.home())
        app.master = Mock()
        app.status = Value('')
        app.busy = False
        app.mounted_path = None
        app.config = {'networkStorages': [dict(server='nas', folder='share', networkName='WORKGROUP')]}
        for name in ('run_button', 'mount_button', 'share_selector', 'settings_button', 'network_browse_button', 'disk_selector', 'disk_refresh_button', 'local_mount_button', 'local_browse_button'):
            setattr(app, name, MagicMock())
        app.share_selector.current.return_value = 0
        app.disk_selector.current.return_value = 0
        return app

    def test_find_disabled_until_mount_even_for_enter(self):
        app = self.app('network')
        app.directory.set('/some/local/path')
        app.update_buttons()
        app.run_button.configure.assert_called_with(state='disabled')
        app.process()
        self.assertEqual(app.status.get(), 'Click Mount first')
        app.mounted_path = Path('/mounted')
        app.update_buttons()
        app.run_button.configure.assert_called_with(state='normal')

    def test_share_changes_clear_mount_and_selection(self):
        app = self.app('network')
        app.mounted_path = Path('/mounted')
        app.network_directory.set('/mounted/Movies')
        app.invalidate()
        self.assertIsNone(app.mounted_path)
        self.assertEqual(app.network_directory.get(), '')
        app.run_button.configure.assert_called_with(state='disabled')

    def test_busy_disables_actions_and_enter(self):
        app = self.app('network')
        app.mounted_path = Path('/mounted')
        app.busy = True
        app.start = Mock()
        app.update_buttons()
        app.process()
        app.mount()
        app.start.assert_not_called()
        for name in ('run_button', 'mount_button', 'settings_button', 'network_browse_button'):
            getattr(app, name).configure.assert_called_with(state='disabled')

    def test_local_find_preserves_paths(self):
        app = self.app('local')
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            (source / 'file.txt').write_text('text')
            app.directory.set(directory)
            app.search_name = Value('my label')
            app.simple_search = Value(True)
            app.result_location = Value(2)
            def synchronous(job, callback, status):
                callback(job())
            app.start = synchronous
            app.process()
            self.assertIn(directory, (source / 'result.csv').read_text())


    def test_network_csv_uses_configured_folder_instead_of_workgroup(self):
        for folder in ('video', '/video/', 'video/Movies'):
            with self.subTest(folder=folder), tempfile.TemporaryDirectory() as directory:
                source = Path(directory)
                (source / 'nested').mkdir()
                (source / 'root.txt').write_text('root')
                (source / 'nested' / 'child.txt').write_text('child')
                app = self.app('network')
                app.config['networkStorages'][0]['folder'] = folder
                app.mounted_path = source
                app.search_name = Value('label')
                app.simple_search = Value(False)
                app.result_location = Value(2)
                app.start = lambda job, callback, status: callback(job())
                app.process()
                with (source / 'result.csv').open(newline='') as stream:
                    rows = list(csv.reader(stream, delimiter=';'))[1:]
                prefix = folder.strip('/')
                self.assertEqual({row[1] for row in rows}, {prefix, prefix + '/nested'})
                self.assertEqual(app.config['networkStorages'][0]['networkName'], 'WORKGROUP')


    def test_network_picker_requires_mount_and_idle_app(self):
        app = self.app('network')
        with patch('gui.filedialog.askdirectory') as picker:
            app.update_buttons()
            app.network_browse_button.configure.assert_called_with(state='disabled')
            app.select_network_directory()
            app.mounted_path = Path('/mounted')
            app.update_buttons()
            app.network_browse_button.configure.assert_called_with(state='normal')
            app.busy = True
            app.select_network_directory()
            picker.assert_not_called()

    def test_network_picker_cancel_retains_selection(self):
        app = self.app('network')
        app.mounted_path = Path('/mounted')
        app.network_directory.set('/mounted/Movies')
        with patch('gui.filedialog.askdirectory', return_value='') as picker:
            app.select_network_directory()
        self.assertEqual(picker.call_args[1]['initialdir'], '/mounted/Movies')
        self.assertEqual(app.network_directory.get(), '/mounted/Movies')

    def test_network_picker_limits_selection_to_mounted_folder(self):
        app = self.app('network')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mounted = root / 'mounted'
            mounted.mkdir()
            (mounted / 'outside-link').symlink_to(root, target_is_directory=True)
            app.mounted_path = mounted
            app.network_directory.set(str(mounted))
            for invalid in (root, mounted / 'outside-link', mounted / 'missing'):
                with self.subTest(invalid=invalid), \
                     patch('gui.filedialog.askdirectory', return_value=str(invalid)), \
                     self.assertLogs('gui', level='WARNING'):
                    app.select_network_directory()
                self.assertEqual(app.network_directory.get(), str(mounted))

    def test_picked_subfolder_drives_listing_and_csv_output(self):
        app = self.app('network')
        with tempfile.TemporaryDirectory() as directory:
            mounted = Path(directory)
            selected = mounted / 'Movies'
            (selected / 'nested').mkdir(parents=True)
            (selected / 'nested' / 'child.txt').write_text('child')
            (selected / 'movie.txt').write_text('movie')
            (mounted / 'outside.txt').write_text('outside selection')
            app.config['networkStorages'][0]['folder'] = 'video'
            app.mounted_path = mounted
            with patch('gui.filedialog.askdirectory', return_value=str(selected)) as picker:
                app.select_network_directory()
            self.assertEqual(picker.call_args[1]['initialdir'], str(mounted))
            self.assertEqual(app.network_directory.get(), str(selected))
            app.search_name = Value('label')
            app.simple_search = Value(False)
            app.result_location = Value(2)
            app.start = lambda job, callback, status: callback(job())
            app.process()
            with (selected / 'result.csv').open(newline='') as stream:
                rows = list(csv.reader(stream, delimiter=';'))[1:]
            self.assertEqual({row[1] for row in rows}, {'video/Movies', 'video/Movies/nested'})
            self.assertEqual({row[0] for row in rows}, {'movie.txt', 'child.txt'})
            # Picking the mounted root again needs no remount.
            with patch('gui.filedialog.askdirectory', return_value=str(mounted)):
                app.select_network_directory()
            self.assertEqual(app.network_directory.get(), str(mounted))
            self.assertEqual(app.mounted_path, mounted)


    def test_default_local_picker_starts_in_home_without_mounting(self):
        app = self.app('local')
        with patch('gui.filedialog.askdirectory', return_value='') as picker:
            app.select_directory()
        self.assertEqual(picker.call_args[1]['initialdir'], str(Path.home()))
        self.assertEqual(app.directory.get(), '')
        app.local_mount_button.configure.assert_not_called()

    def test_unmounted_local_disk_blocks_browse_and_find(self):
        app = self.app('local')
        app.directory.set('/old/disk/folder')
        app.disks = [dict(device='/dev/sdb1', label='Photos', mountpoint=None, size='1T', initial=None)]
        app.select_disk()
        self.assertEqual(app.directory.get(), '')
        self.assertIsNone(app.local_root)
        app.local_browse_button.configure.assert_called_with(state='disabled')
        app.run_button.configure.assert_called_with(state='disabled')
        app.local_mount_button.configure.assert_called_with(text='Mount', state='normal')
        with patch('gui.filedialog.askdirectory') as picker:
            app.select_directory()
            app.process()
        picker.assert_not_called()
        self.assertEqual(app.status.get(), 'Click Mount first')

    def test_mounted_local_disk_starts_browsing_at_its_mountpoint(self):
        app = self.app('local')
        with tempfile.TemporaryDirectory() as directory:
            app.disks = [dict(device='/dev/sdb1', label='Photos', mountpoint=directory, size='1T', initial=directory)]
            app.select_disk()
            self.assertEqual(app.local_root, Path(directory))
            app.local_browse_button.configure.assert_called_with(state='normal')
            app.local_mount_button.configure.assert_called_with(text='Mounted', state='disabled')
            with patch('gui.filedialog.askdirectory', return_value='') as picker:
                app.select_directory()
            self.assertEqual(picker.call_args[1]['initialdir'], directory)

    def test_local_picker_rejects_folder_outside_selected_disk(self):
        app = self.app('local')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            disk = root / 'disk'
            disk.mkdir()
            (disk / 'outside-link').symlink_to(root, target_is_directory=True)
            app.local_root = disk
            app.local_initial = str(disk)
            for selection in (root, disk / 'outside-link', disk / 'missing'):
                with self.subTest(selection=selection), \
                     patch('gui.filedialog.askdirectory', return_value=str(selection)), \
                     self.assertLogs('gui', level='WARNING'):
                    app.select_directory()
                self.assertEqual(app.directory.get(), '')
            selected = disk / 'Photos'
            selected.mkdir()
            with patch('gui.filedialog.askdirectory', return_value=str(selected)):
                app.select_directory()
            self.assertEqual(app.directory.get(), str(selected))

    def test_local_mount_updates_selected_disk_and_enables_listing(self):
        app = self.app('local')
        app.disks = [dict(device='/dev/sdb1', label='Photos', mountpoint=None, size='1T', initial=None)]
        app.select_disk()
        app.start = lambda job, callback, status: callback(job())
        with tempfile.TemporaryDirectory() as directory:
            with patch('gui.mount_disk', return_value=Path(directory)) as mount:
                app.mount_local()
            app.update_buttons()
            self.assertEqual(app.directory.get(), directory)
            self.assertEqual(app.disks[0]['mountpoint'], directory)
            app.disk_selector.current.assert_called_with(0)
            app.run_button.configure.assert_called_with(state='normal')
            mount.assert_called_once_with(app.disks[0])

    def test_refresh_handles_removed_disk_and_returns_to_default(self):
        app = self.app('local')
        app.disks = [dict(device='/dev/sdb1', label='Photos', mountpoint='/media/me/Photos', size='1T', initial='/media/me/Photos')]
        app.select_disk()
        app.start = lambda job, callback, status: callback(job())
        from local_storage import default_disk
        with patch('gui.discover_disks', return_value=[default_disk()]):
            app.refresh_disks()
        self.assertIsNone(app.current_disk()['device'])
        self.assertEqual(app.directory.get(), '')
        self.assertEqual(app.local_initial, str(Path.home()))

    def test_busy_disables_local_disk_actions(self):
        app = self.app('local')
        app.busy = True
        app.update_buttons()
        app.local_browse_button.configure.assert_called_with(state='disabled')
        app.disk_refresh_button.configure.assert_called_with(state='disabled')
        app.disk_selector.configure.assert_called_with(state='disabled')
        with patch('gui.filedialog.askdirectory') as picker, patch('gui.mount_disk') as mount:
            app.mount_local()
            app.select_directory()
            app.select_disk()
            app.refresh_disks()
        picker.assert_not_called()
        mount.assert_not_called()


if __name__ == '__main__':
    unittest.main()
