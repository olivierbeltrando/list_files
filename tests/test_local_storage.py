import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import local_storage


def volume(device='/dev/sdb1', mountpoint=None):
    return dict(device=device, mountpoint=mountpoint, label='Photos', size='1T', initial=mountpoint)


class LocalStorageTests(unittest.TestCase):
    def test_discovery_flattens_partitions_filters_members_and_deduplicates(self):
        mounted = dict(name='/dev/sdb1', label='Photos', fstype='ext4',
                       mountpoints=['/media/me/Photos'], size='1T', type='part')
        data = {'blockdevices': [
            dict(name='/dev/sda', children=[
                dict(name='/dev/sda1', fstype='ext4', mountpoints=['/'], type='part'),
                dict(name='/dev/sda2', fstype='swap', mountpoints=[None], type='part')]),
            dict(name='/dev/sdb', children=[mounted]), mounted,
            dict(name='/dev/sdc1', fstype='ntfs', mountpoints=[None], type='part'),
            dict(name='/dev/sdd1', fstype='crypto_LUKS', mountpoints=[None], type='part'),
            dict(name='/dev/loop0', fstype='squashfs', mountpoints=['/snap/a'], type='loop'),
        ]}
        with patch('local_storage.platform.system', return_value='Linux'), \
             patch('local_storage.shutil.which', return_value='/usr/bin/lsblk'), \
             patch('local_storage.subprocess.run', return_value=Mock(stdout=json.dumps(data))):
            disks = local_storage.discover_disks()
        self.assertIsNone(disks[0]['device'])
        self.assertEqual(disks[0]['initial'], str(Path.home()))
        self.assertEqual([d['device'] for d in disks[1:]], ['/dev/sdb1', '/dev/sdc1'])
        self.assertEqual(disks[1]['mountpoint'], '/media/me/Photos')
        self.assertIsNone(disks[2]['mountpoint'])

    def test_default_filesystem_never_needs_mount_command(self):
        with patch('local_storage.subprocess.run') as run:
            self.assertEqual(local_storage.mount_disk(local_storage.default_disk()), Path(Path.home().anchor))
        run.assert_not_called()

    def test_already_mounted_disk_is_reused(self):
        with patch('local_storage.platform.system', return_value='Linux'), \
             patch('local_storage._linux_disks', return_value=[volume(mountpoint='/media/me/Photos')]), \
             patch('local_storage.subprocess.run') as run:
            result = local_storage.mount_disk(volume())
        self.assertEqual(result, Path('/media/me/Photos'))
        run.assert_not_called()

    def test_mount_uses_desktop_tool_and_discovers_real_mountpoint(self):
        with patch('local_storage.platform.system', return_value='Linux'), \
             patch('local_storage._linux_disks', side_effect=[[volume()], [volume(mountpoint='/media/me/My Photos')]]), \
             patch('local_storage.shutil.which', return_value='/usr/bin/udisksctl'), \
             patch('local_storage.subprocess.run', return_value=Mock(returncode=0)) as run:
            result = local_storage.mount_disk(volume())
        self.assertEqual(result, Path('/media/me/My Photos'))
        self.assertEqual(run.call_args[0][0], ['udisksctl', 'mount', '--block-device', '/dev/sdb1'])
        self.assertEqual(run.call_args[1]['stdin'], subprocess.DEVNULL)

    def test_mount_failures_are_explicit(self):
        cases = [('removed', [], True, Mock(returncode=0), 'no longer available'),
                 ('tool missing', [volume()], False, Mock(returncode=0), 'udisksctl'),
                 ('denied', [volume()], True, Mock(returncode=1, stderr='Not authorized'), 'Not authorized')]
        for name, disks, tool, result, message in cases:
            with self.subTest(case=name), \
                 patch('local_storage.platform.system', return_value='Linux'), \
                 patch('local_storage._linux_disks', return_value=disks), \
                 patch('local_storage.shutil.which', return_value='/usr/bin/udisksctl' if tool else None), \
                 patch('local_storage.subprocess.run', return_value=result), \
                 self.assertRaisesRegex(RuntimeError, message):
                local_storage.mount_disk(volume())

    def test_no_disks_found_keeps_default_filesystem(self):
        with patch('local_storage.platform.system', return_value='Linux'), \
             patch('local_storage._linux_disks', return_value=[]):
            self.assertEqual(len(local_storage.discover_disks()), 1)


if __name__ == '__main__':
    unittest.main()
