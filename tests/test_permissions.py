"""Regression checks for NAS folders that deny traversal or file metadata access."""
import errno
import os
from pathlib import Path
import queue
import tempfile
import unittest
from unittest.mock import Mock, patch

import list_files
import test_gui
from test_gui import Value


class PermissionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.source = Path(temporary.name)
        self.denied = self.source / 'video'
        self.denied.mkdir()
        (self.denied / 'hidden.txt').write_text('hidden')
        (self.source / 'visible.txt').write_text('visible')
        self.real_scandir = os.scandir

    def scan_with_denial(self, path):
        if Path(path) == self.denied:
            raise PermissionError(errno.EACCES, 'Permission denied', str(path))
        return self.real_scandir(path)

    def test_denied_subfolder_logs_and_preserves_accessible_files(self):
        skipped = []
        with patch('os.scandir', side_effect=self.scan_with_denial), \
             self.assertLogs('list_files', level='WARNING') as logged:
            files = list_files.find_files(str(self.source), '', False, skipped.append)
        self.assertEqual([row[0] for row in files], ['visible.txt'])
        self.assertEqual(len(skipped), 1)
        self.assertIn(str(self.denied), '\n'.join(logged.output))

    def test_denied_root_still_fails(self):
        with patch('os.scandir', side_effect=PermissionError(errno.EACCES, 'Permission denied', str(self.source))):
            with self.assertRaises(PermissionError):
                list_files.find_files(str(self.source), '', False)

    def test_connection_errors_still_fail(self):
        with patch('os.scandir', side_effect=OSError(errno.EIO, 'I/O error', str(self.denied))):
            with self.assertRaises(OSError):
                list_files.find_files(str(self.source), '', False)

    def test_denied_file_stat_is_reported_in_both_modes(self):
        real_stat = os.stat
        def stat_with_denial(path, *args, **kwargs):
            if Path(path) == self.source / 'visible.txt':
                raise PermissionError(errno.EACCES, 'Permission denied', str(path))
            return real_stat(path, *args, **kwargs)
        for simple in (True, False):
            skipped = []
            with patch('os.stat', side_effect=stat_with_denial), self.assertLogs('list_files', level='WARNING'):
                files = list_files.find_files(str(self.source), '', simple, skipped.append)
            self.assertNotIn('visible.txt', [row[0] for row in files])
            self.assertEqual(len(skipped), 1)

    def test_gui_marks_partial_result_as_warning(self):
        app = test_gui.GuiStateTests().app('local')
        app.directory.set(str(self.source))
        app.search_name = Value('label')
        app.simple_search = Value(False)
        app.result_location = Value(2)
        app.start = lambda job, callback, status: callback(job())
        with patch('os.scandir', side_effect=self.scan_with_denial), self.assertLogs('list_files', level='WARNING'):
            app.process()
        self.assertIn('1 inaccessible paths skipped', app.status.get())
        self.assertIn('1 files written', app.status.get())
        self.assertEqual(app.results[1][0][0], 'visible.txt')
        self.assertTrue((self.source / 'result.csv').exists())

    def test_background_failures_are_logged_and_displayed(self):
        app = test_gui.GuiStateTests().app('local')
        app.completed = queue.Queue()
        app.after = Mock()
        error = PermissionError(errno.EACCES, 'Permission denied', str(self.source))
        def failed_job():
            raise error
        class ImmediateThread:
            def __init__(self, target, daemon):
                self.target = target
            def start(self):
                self.target()
        callback = Mock()
        with patch('gui.threading.Thread', ImmediateThread), self.assertLogs('gui', level='ERROR') as logged:
            app.start(failed_job, callback, 'Searching')
        app.poll()
        self.assertIn('PermissionError', '\n'.join(logged.output))
        self.assertIn('Permission denied', app.status.get())
        callback.assert_not_called()
        self.assertFalse(app.busy)


if __name__ == '__main__':
    unittest.main()
