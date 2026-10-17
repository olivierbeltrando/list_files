"""Headless checks for the source/mount state gates, including Return shortcuts."""
import csv
import unittest
from unittest.mock import Mock, patch
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
        app.status = Value('')
        app.busy = False
        app.mounted_path = None
        app.results = None
        app.config = {'networkStorages': [dict(server='nas', folder='share', networkName='WORKGROUP')]}
        for name in ('run_button', 'copy_button', 'mount_button', 'share_selector', 'settings_button'):
            setattr(app, name, Mock())
        app.share_selector.current.return_value = 0
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

    def test_share_changes_clear_mount_and_results(self):
        app = self.app('network')
        app.mounted_path = Path('/mounted')
        app.results = ('source', ['file'])
        app.invalidate()
        self.assertIsNone(app.mounted_path)
        self.assertIsNone(app.results)
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
        for name in ('run_button', 'copy_button', 'mount_button', 'settings_button'):
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
            self.assertEqual(app.results[1][0][0], 'file.txt')


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
                self.assertTrue(all(str(source) in row[1] for row in app.results[1]))


if __name__ == '__main__':
    unittest.main()
