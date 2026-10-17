import csv
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import list_files
from network_storage import Settings, _authenticate, find_mount, mount_storage, storage_uri, validate_settings


class NetworkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.storage = dict(type='smb', server='nas', folder='share/sub folder', credName='main')
        self.secrets = {'main': {'user': 'alice', 'password': 'secret'}}
        self.config = {'networkStorages': [self.storage]}

    def test_settings_roundtrip_and_private_permissions(self):
        settings = Settings(self.root / 'settings')
        self.assertEqual(settings.load(), ({'networkStorages': []}, {}))
        settings.save(self.config, self.secrets)
        config, secrets = settings.load()
        self.assertEqual(config['networkStorages'][0]['networkName'], 'WORKGROUP')
        self.assertEqual(secrets, self.secrets)
        if os.name == 'posix':
            self.assertEqual(settings.directory.stat().st_mode & 0o777, 0o700)
            for name in ('config.json', 'secrets.json'):
                self.assertEqual((settings.directory / name).stat().st_mode & 0o777, 0o600)
        settings.save(config, secrets)
        self.assertEqual(len(list(settings.directory.iterdir())), 2)

    def test_invalid_configs(self):
        for folder in ('../share', 'share/../escape', 'share//folder', ''):
            with self.subTest(folder=folder), self.assertRaises(ValueError):
                validate_settings({'networkStorages': [dict(self.storage, folder=folder)]}, self.secrets)
        with self.assertRaises(ValueError):
            validate_settings(self.config, {'main': {'user': 'alice', 'password': 'bad\nline'}})
        with self.assertRaises(ValueError):
            validate_settings(self.config, {})
        settings = Settings(self.root)
        (self.root / 'config.json').write_text('[]')
        with self.assertRaises(ValueError):
            settings.load()

    def test_uri_encoding(self):
        self.assertEqual(storage_uri(self.storage), 'smb://nas/share/sub%20folder')

    def test_discover_mount_optional_attributes_and_subdirectory(self):
        mount = self.root / 'gvfs' / 'smb-share:server=NAS,share=share,user=alice,domain=WORKGROUP'
        (mount / 'sub folder').mkdir(parents=True)
        self.assertEqual(find_mount(self.storage, self.secrets['main'], self.root), mount / 'sub folder')
        self.assertIsNone(find_mount(self.storage, {'user': 'bob'}, self.root))
        mount.rename(mount.with_name('smb-share:server=nas,share=share'))
        self.assertIsNotNone(find_mount(self.storage, self.secrets['main'], self.root))

    def authenticate_with_script(self, script, timeout=3):
        real_popen = subprocess.Popen
        def launch(argv, **kwargs):
            self.assertEqual(argv, ['gio', 'mount', 'smb://nas/share'])
            return real_popen([sys.executable, '-u', '-c', script], **kwargs)
        with patch('network_storage.subprocess.Popen', side_effect=launch):
            return _authenticate('smb://nas/share', self.secrets['main'], 'WORKGROUP', timeout)

    def test_optional_authentication_prompts(self):
        for fields in [('Password',), ('User', 'Domain', 'Password'), ()]:
            script = "import sys\n"
            expected = {'User': 'alice', 'Domain': 'WORKGROUP', 'Password': 'secret'}
            for field in fields:
                script += f"print({field!r} + ' [default]: ', end='', flush=True)\n"
                script += f"assert sys.stdin.readline().rstrip('\\n') == {expected[field]!r}\n"
            self.assertEqual(self.authenticate_with_script(script), 0)

    def test_rejected_authentication_and_timeout(self):
        script = "import sys\nfor _ in range(2):\n print('Password: ',end='',flush=True)\n sys.stdin.readline()\n"
        with self.assertRaisesRegex(RuntimeError, 'rejected'):
            self.authenticate_with_script(script)
        with self.assertRaisesRegex(RuntimeError, 'timed out'):
            self.authenticate_with_script('import time; time.sleep(5)', timeout=.05)

    def test_mount_and_platform_gate(self):
        with patch('network_storage.platform.system', return_value='Windows'):
            with self.assertRaisesRegex(RuntimeError, 'Linux'):
                mount_storage(self.storage, self.secrets['main'])
        with patch('network_storage.platform.system', return_value='Linux'), \
             patch('network_storage.shutil.which', return_value='/usr/bin/gio'), \
             patch('network_storage._authenticate', return_value=1) as auth, \
             patch('network_storage.find_mount', return_value=self.root):
            self.assertEqual(mount_storage(self.storage, self.secrets['main']), self.root)
            self.assertEqual(auth.call_args[0][0], 'smb://nas/share')

    def test_recursive_list_prefix_csv_and_copy(self):
        source = self.root / 'source'
        (source / 'nested').mkdir(parents=True)
        (source / 'nested' / 'été;"test.txt').write_text('payload')
        (source / 'zero').touch()
        rows = list_files.find_files(str(source), 'label', False)
        self.assertEqual(len(rows), 2)
        exported = list_files.with_path_prefix(rows, source, 'WORKGROUP')
        self.assertEqual({r[1] for r in exported}, {'WORKGROUP', 'WORKGROUP/nested'})
        self.assertTrue(all(str(source) in r[1] for r in rows))
        output = self.root / 'result.csv'
        list_files.write_cvs(exported, output)
        with output.open(newline='') as stream:
            self.assertEqual(list(csv.reader(stream, delimiter=';'))[1:], exported)
        destination = self.root / 'dest'
        self.assertEqual(list_files.copy_files(rows, source, destination), 2)
        self.assertEqual((destination / 'nested' / 'été;"test.txt').read_text(), 'payload')
        with self.assertRaises(FileExistsError):
            list_files.copy_files(rows, source, destination)
        with self.assertRaises(ValueError):
            list_files.copy_files(rows, source, source / 'inside')

    def test_copy_rejects_escaping_links(self):
        source = self.root / 'source'
        source.mkdir()
        outside = self.root / 'outside'
        outside.write_text('private')
        (source / 'link').symlink_to(outside)
        rows = list_files.find_files(str(source), '', True)
        with self.assertRaises(ValueError):
            list_files.copy_files(rows, source, self.root / 'dest')


if __name__ == '__main__':
    unittest.main()
