"""Local filesystem discovery and desktop-managed mounting, without Python packages."""
import json
import os
import platform
import shutil
import subprocess
from pathlib import Path


_EXCLUDED_FILESYSTEMS = {'swap', 'crypto_LUKS', 'LVM2_member', 'linux_raid_member', 'zfs_member'}


def default_disk():
    home = Path.home()
    return {'device': None, 'label': 'Default filesystem', 'mountpoint': home.anchor,
            'size': '', 'initial': str(home)}


def _linux_disks():
    if not shutil.which('lsblk'):
        raise RuntimeError('Disk discovery needs the system lsblk command (util-linux).')
    result = subprocess.run(
        ['lsblk', '--json', '--paths', '--output', 'NAME,LABEL,FSTYPE,MOUNTPOINTS,SIZE,TYPE'],
        capture_output=True, text=True, timeout=15, check=True)
    data = json.loads(result.stdout)
    disks, seen = [], set()

    def visit(nodes):
        for node in nodes:
            device = node.get('name', '')
            filesystem = node.get('fstype')
            if (device.startswith('/dev/') and device not in seen and filesystem
                    and filesystem not in _EXCLUDED_FILESYSTEMS and node.get('type') != 'loop'):
                seen.add(device)
                mounts = [p for p in node.get('mountpoints', []) if p and p.startswith('/')]
                # The default entry already represents the OS filesystem.
                if '/' not in mounts:
                    mountpoint = next((p for p in mounts if p.startswith(('/media/', '/run/media/'))),
                                      mounts[0] if mounts else None)
                    disks.append({'device': device, 'label': node.get('label') or device,
                                  'mountpoint': mountpoint, 'size': node.get('size') or '',
                                  'initial': mountpoint})
            visit(node.get('children', []))
    visit(data.get('blockdevices', []))
    return disks


def discover_disks():
    disks = [default_disk()]
    if platform.system() == 'Linux':
        disks.extend(_linux_disks())
    elif os.name == 'nt':
        for letter in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
            root = Path(letter + ':\\')
            if root.is_dir() and str(root) != disks[0]['mountpoint']:
                disks.append({'device': str(root), 'label': str(root), 'mountpoint': str(root),
                              'size': '', 'initial': str(root)})
    return disks


def mount_disk(disk):
    if disk['device'] is None:
        return Path(disk['mountpoint'])
    if platform.system() != 'Linux':
        if disk['mountpoint'] and Path(disk['mountpoint']).is_dir():
            return Path(disk['mountpoint'])
        raise RuntimeError('Automatic disk mounting is currently available on Linux only.')

    def current():
        return next((entry for entry in _linux_disks() if entry['device'] == disk['device']), None)

    entry = current()
    if entry is None:
        raise RuntimeError('Disk is no longer available. Refresh the disk list.')
    if entry['mountpoint']:
        return Path(entry['mountpoint'])
    if not shutil.which('udisksctl'):
        raise RuntimeError('Disk mounting needs the system udisksctl command (udisks2).')
    result = subprocess.run(['udisksctl', 'mount', '--block-device', entry['device']],
                            stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise RuntimeError('Cannot mount disk: ' + (result.stderr.strip() or 'udisksctl failed'))
    entry = current()
    if entry is None or not entry['mountpoint']:
        raise RuntimeError('Disk mountpoint is unavailable. Refresh the disk list and retry.')
    return Path(entry['mountpoint'])


def disk_label(disk):
    if disk['device'] is None:
        return 'Default filesystem (already mounted)'
    state = disk['mountpoint'] or 'not mounted'
    name = disk['label']
    if name != disk['device']:
        name += ' — ' + disk['device']
    return f"{name} ({disk['size']}; {state})"
