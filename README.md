# list_files

List files in a local folder or a Linux SMB share and export `result.csv`.
No third-party Python packages are needed. Start the interface with:

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

Local disk discovery uses `lsblk` (util-linux). Mounting an unmounted local disk
uses `udisksctl` (udisks2), with the desktop's usual authorization dialog if needed.
These are system tools, not Python packages. If needed on Debian/Ubuntu/Mint:

```sh
sudo apt install util-linux udisks2
```

Automatic disk discovery/mounting is implemented on Linux. Windows also lists
available drive letters; other platforms retain the default filesystem browser.
Locked encrypted disks must first be unlocked in the desktop file manager.

## Listing files

- **Local:** Pick a disk/filesystem from the selector. Already mounted disks are
  immediately available; otherwise click **Mount** first. Then **Browse…** to pick
  a folder on that disk and **Find / generate file list**. The default filesystem
  needs no mounting and starts Browse in your home directory. Other disks start
  Browse at their actual mountpoint (for example `/media/your-user/MyDisk`).
  **Refresh disks** updates the list after plugging in or removing a disk.
  Changing disks clears the previous selected folder. Disks remain mounted on
  app exit.
- **Network:** Select a configured NAS share and click **Mount**. Use **Browse…**
  beside the mounted folder to choose a subfolder, then **Find / generate file
  list**. Browse and Find are disabled until Mount succeeds, including when a
  share is already mounted. You can pick the mounted root again or another
  subfolder without remounting. Switching shares/modes or saving settings requires
  mounting again. Cancel keeps the current folder. The picker accepts folders
  inside the configured mounted folder only. Output saved in the selected
  directory goes into that subfolder.
- The location label is CSV metadata, as in the original application; it does not
  filter filenames. Select the recursive option by unchecking “Only search the
  selected folder”.
- Mounting and finding run in background threads so the window remains
  responsive. Mounts are managed by the desktop and remain mounted on app exit.

The CSV `path` column retains absolute folder paths in Local mode. In Network
mode the mounted source path is replaced by the configured `folder`, followed by
the relative subfolder, including any subfolder chosen with Browse. For example,
choosing `Movies` under `video` produces `video/Movies/2026` for files in its
`2026` subfolder. The separate
`:location_label` column still contains the label you entered. The real GVFS path
is used for reading, never the CSV prefix.

Unreadable subfolders/files are skipped with a warning in the logs and a skipped
path count in the UI, so a CSV may be incomplete. An unreadable source root or
other I/O failure stops the operation and is logged with a traceback.

## Settings

Open **Shares / credentials…**, create a named credential on the Credentials tab,
then create a share on the Shares tab and select that name from the credential
picker. Only registered credentials can be selected; the picker updates when you
add, rename or delete credentials. **Apply entry** adds
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
mount discovery, local disk discovery/mount commands, credential picker updates,
UI source gates, listing prefixes and CSV escaping.
They run without a display or SMB server. A live NAS/desktop mount remains a
manual integration check.
