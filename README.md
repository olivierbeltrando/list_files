# list_files

List files in a local folder or a Linux SMB share, export `result.csv`, and
optionally copy the listed files to another folder. No third-party Python packages
are needed. Start the interface with:

```sh
python3 gui.py
```

Python must include Tkinter (on Debian/Ubuntu/Mint: `python3-tk`). Network mode
uses the Linux desktop's `gio` command and GVFS SMB/FUSE support. On
Debian/Ubuntu/Mint, if these system components are missing:

```sh
sudo apt install libglib2.0-bin gvfs-backends gvfs-fuse
```

Run from your normal logged-in graphical desktop session, without sudo. Network
mode is disabled on other operating systems. Local mode continues to work there.

## Sources and copying

- **Local:** Browse for a folder, then **Find / generate file list**.
- **Network:** Select a configured NAS share, click **Mount**, then **Find / generate
  file list**. Find is disabled until Mount succeeds, including when a share is
  already mounted. Changing the source or saving settings requires mounting again.
- The location label is CSV metadata, as in the original application; it does not
  filter filenames. Select the recursive option by unchecking “Only search the
  selected folder”.
- **Copy files…** copies the files from the last successful Find into a destination
  you choose, preserving relative subfolders. Existing destination files are never
  overwritten. Choose a destination outside the source. Copies run in the
  background; if one fails, earlier completed files remain at the destination.
  File symlinks are dereferenced only when their targets remain inside the source.
- Mounting, finding and copying run in background threads so the window remains
  responsive. Mounts are managed by the desktop and remain mounted on app exit.

The CSV `path` column retains absolute folder paths in Local mode. In Network
mode the mounted source path is replaced by the configured `folder`, followed by
the relative subfolder, for example `video/Movies/2026` when `folder` is `video`. The separate
`:location_label` column still contains the label you entered. The real GVFS path
is used for reading and copying, never the CSV prefix.

Unreadable subfolders/files are skipped with a warning in the logs and a skipped
path count in the UI, so a CSV may be incomplete. An unreadable source root or
other I/O failure stops the operation and is logged with a traceback.

## Settings

Open **Shares / credentials…**, create a named credential on the Credentials tab,
then create a share on the Shares tab referencing that name. **Apply entry** adds
or updates each entry in the dialog; **Save settings** writes the changes. Cancel
discards unapplied/saved dialog edits. Credentials can be renamed; referenced
shares are updated automatically. Delete or update referencing shares before
deleting a credential.

Settings live in `~/.list-files/`. Both files are JSON objects (JSON does not
support comments).

`config.json`:

```json
{
  "networkStorages": [
    {
      "type": "smb",
      "folder": "Photos/2026",
      "server": "nas.local",
      "credName": "myCred",
      "networkName": "WORKGROUP"
    }
  ]
}
```

`folder` begins with the SMB share name, optionally followed by subfolders. Use a
hostname or IP for `server`, without `smb://`. `networkName` is the SMB
workgroup/domain; it defaults to `WORKGROUP` when omitted. It does not affect CSV
paths.

`secrets.json`:

```json
{
  "myCred": {
    "user": "user",
    "password": "1234"
  }
}
```

Passwords are stored in plain text as requested. On Linux, settings saved by the
app have directory permissions `0700` and file permissions `0600`. Passwords are
passed to GIO through a pipe, never command-line arguments. Credential fields
must be single-line strings of at most 254 UTF-8 bytes, due to GIO's prompt limit.
Do not commit these personal settings to Git.

The mount directory is discovered under `$XDG_RUNTIME_DIR/gvfs`, falling back to
`/run/user/<your uid>/gvfs`, rather than assuming UID 1000. GIO mounts the share
root and the app checks the configured subfolder exists. If mounting fails,
check the server, share, credentials, workgroup/domain, and desktop GVFS support.

The original local command-line interface is also available:

```sh
python3 list_files.py /path/to/folder "Location label"
```

It searches recursively and writes `result.csv` in the current working directory.

## Tests

```sh
python3 -m unittest discover -s tests -v
```

Tests cover settings validation/permissions, GIO prompt handling and timeouts,
mount discovery, UI source gates, listing prefixes, CSV escaping and copying.
They run without a display or SMB server. A live NAS/desktop mount remains a
manual integration check.
