"""Settings and Linux SMB access using the desktop's GIO/GVFS tools."""
import json
import os
import platform
import re
import select
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import quote, unquote


class Settings:
    def __init__(self, directory=None):
        self.directory = Path(directory) if directory else Path.home() / '.list-files'

    def load(self):
        def read(name, default):
            path = self.directory / name
            if not path.exists():
                return default
            with path.open(encoding='utf-8') as stream:
                return json.load(stream)
        config = read('config.json', {'networkStorages': []})
        secrets = read('secrets.json', {})
        validate_settings(config, secrets)
        for storage in config['networkStorages']:
            storage.setdefault('networkName', 'WORKGROUP')
        return config, secrets

    def save(self, config, secrets):
        validate_settings(config, secrets)
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.directory.chmod(0o700)
        # Each file is replaced atomically, with private permissions from creation.
        for name, value in [('secrets.json', secrets), ('config.json', config)]:
            fd, temporary = tempfile.mkstemp(dir=self.directory, prefix='.' + name)
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                    json.dump(value, stream, indent=2, ensure_ascii=False)
                    stream.write('\n')
                os.replace(temporary, self.directory / name)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)


def validate_settings(config, secrets):
    if not isinstance(config, dict) or not isinstance(config.get('networkStorages'), list):
        raise ValueError('config.json must contain a networkStorages array')
    if not isinstance(secrets, dict):
        raise ValueError('secrets.json must contain a credential object')
    for name, credential in secrets.items():
        if not name or not isinstance(credential, dict):
            raise ValueError('Each credential needs a name and user/password fields')
        for field in ('user', 'password'):
            value = credential.get(field)
            if not isinstance(value, str) or any(c in value for c in '\r\n\0'):
                raise ValueError('Credential fields must be single-line strings')
            if len(value.encode('utf-8')) > 254:
                raise ValueError('Credential fields must be at most 254 UTF-8 bytes (GIO limit)')
        if not credential['user']:
            raise ValueError('Credential user cannot be empty')
    for storage in config['networkStorages']:
        if not isinstance(storage, dict) or storage.get('type') != 'smb':
            raise ValueError('Only smb storages are supported')
        for field in ('server', 'folder', 'credName'):
            if not isinstance(storage.get(field), str) or not storage[field].strip():
                raise ValueError('Each SMB storage needs server, folder and credName')
        server = storage['server']
        if any(c in server for c in '/\\@?#\r\n\0') or server.startswith('-'):
            raise ValueError('Server must be a hostname or IP address, without smb://')
        parts = storage['folder'].strip('/').split('/')
        if not parts[0] or any(p in ('.', '..', '') for p in parts) or '\\' in storage['folder']:
            raise ValueError('Folder must be share or share/subfolder, without . or ..')
        network = storage.get('networkName', 'WORKGROUP')
        if not isinstance(network, str) or not network.strip() or any(c in network for c in '/\\\r\n\0'):
            raise ValueError('networkName must be a nonempty workgroup/domain name')
        if len(network.encode('utf-8')) > 254:
            raise ValueError('networkName must be at most 254 UTF-8 bytes (GIO limit)')
        if storage['credName'] not in secrets:
            raise ValueError('Storage references an unknown credential')


def storage_uri(storage):
    return 'smb://' + storage['server'] + '/' + quote(storage['folder'].strip('/'), safe='/')


def find_mount(storage, credential, runtime=None):
    """Discover the real GVFS name, whose optional attributes vary by desktop."""
    root = Path(runtime or os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')) / 'gvfs'
    share, *subfolders = storage['folder'].strip('/').split('/')
    if not root.is_dir():
        return None
    for entry in root.iterdir():
        if not entry.name.startswith('smb-share:'):
            continue
        attributes = dict(part.split('=', 1) for part in entry.name[10:].split(',') if '=' in part)
        attributes = {key: unquote(value) for key, value in attributes.items()}
        if attributes.get('server', '').casefold() != storage['server'].casefold():
            continue
        if attributes.get('share', '').casefold() != share.casefold():
            continue
        if 'user' in attributes and attributes['user'] != credential['user']:
            continue
        if 'domain' in attributes and attributes['domain'].casefold() != storage.get('networkName', 'WORKGROUP').casefold():
            continue
        target = entry.joinpath(*subfolders)
        if target.is_dir():
            return target
    return None


def _authenticate(uri, credential, domain, timeout=45):
    """Answer GIO's optional prompts individually; never expose a password in argv."""
    env = dict(os.environ, LC_ALL='C', LANG='C')
    process = subprocess.Popen(['gio', 'mount', uri], stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
    deadline = time.monotonic() + timeout
    buffer = b''
    answers = {'User': credential['user'], 'Domain': domain, 'Password': credential['password']}
    counts = dict.fromkeys(answers, 0)
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError('SMB mount timed out. Check the server and your desktop session.')
            readable, _, _ = select.select([process.stdout], [], [], min(remaining, .2))
            if not readable:
                continue
            chunk = os.read(process.stdout.fileno(), 4096)
            if not chunk:
                break
            buffer = (buffer + chunk)[-16384:]
            prompt = re.search(rb'(User|Domain|Password)(?: \[[^\r\n]*\])?: $', buffer)
            if prompt:
                field = prompt.group(1).decode('ascii')
                counts[field] += 1
                if counts[field] > 1:
                    raise RuntimeError('SMB authentication was rejected. Check the credentials and workgroup.')
                process.stdin.write((answers[field] + '\n').encode('utf-8'))
                process.stdin.flush()
                buffer = b''
        code = process.wait(timeout=max(.1, deadline - time.monotonic()))
        # Do not include subprocess output: it can contain authentication details.
        return code
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()
        process.stdin.close()
        process.stdout.close()


def mount_storage(storage, credential):
    if platform.system() != 'Linux':
        raise RuntimeError('Network mode is only available on Linux')
    if not shutil.which('gio'):
        raise RuntimeError('GIO is missing. Install the system libglib2.0-bin package.')
    # Mount the share root; the configured folder may be a directory within it.
    root_storage = dict(storage, folder=storage['folder'].strip('/').split('/')[0])
    code = _authenticate(storage_uri(root_storage), credential, storage.get('networkName', 'WORKGROUP'))
    target = find_mount(storage, credential)
    if target is not None:
        return target  # Also handles GIO reporting that this share is already mounted.
    if code:
        raise RuntimeError('Cannot mount SMB share. Check credentials, server/share and GVFS SMB support (gvfs-backends).')
    raise RuntimeError('Share mounted but folder is unavailable through GVFS. Check the folder and gvfs-fuse in your desktop session.')
