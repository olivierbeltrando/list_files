# -*- coding: utf-8 -*-

import string
import platform

# logger -----------------------------------------------
import logging
FORMAT = '%(asctime)-15s - %(levelname)s - %(message)s'
logging.basicConfig(format=FORMAT)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
# ------------------------------------------------------


columns = ['filename', 'path', 'type', 'size', ':location_label']


def discard_invalid_chars(_string):
    return ''.join(char for char in _string if char in string.printable)


megabyte = 1024 * 1024


def add_file_to_list(_list,
                     _filename,
                     _parent_directory,
                     _size,
                     _location_label):
    # replacing the ';' by '-' because of csv files
    # filename = discard_invalid_chars(_filename)
    filename = _filename
    if filename != _filename:
        logger.warn(
            "this file was renamed to avoid errors: {}".format(filename)
        )
    _list.append([
        filename,
        _parent_directory,
        filename.split('.')[-1],
        '%.2f Mo' % (_size/megabyte),
        _location_label,
    ])

# find the files


def find_files(_dir_to_search, _location_label, _simpleSearch=True, _on_error=None):
    """List accessible files; report skipped permission errors through _on_error.

    A denied source root and other I/O failures still abort the scan. Denied
    children are logged and skipped so one private folder cannot discard results.
    """
    import os
    import stat
    ret_list = []
    skipped = 0
    dir_to_search = os.path.abspath(_dir_to_search)
    logger.debug('raw input directory : %s', _dir_to_search)
    logger.info('The directory to explore: %s', dir_to_search)

    def handle_error(error):
        nonlocal skipped
        if (not isinstance(error, PermissionError) or not error.filename
                or os.path.abspath(error.filename) == dir_to_search):
            raise error
        skipped += 1
        logger.warning('Skipping inaccessible path: %s', error)
        if _on_error is not None:
            _on_error(error)

    def add_file(parent, name):
        full_filename = os.path.join(parent, name)
        try:
            info = os.stat(full_filename)
        except OSError as error:
            handle_error(error)
            return
        if stat.S_ISREG(info.st_mode):
            add_file_to_list(ret_list, name, parent, info.st_size, _location_label)

    if _simpleSearch:
        logger.info('Simple search has been activated')
        for name in os.listdir(dir_to_search):
            add_file(dir_to_search, name)
    else:
        logger.info('Recursive search has been activated')
        for root, dirs, files in os.walk(dir_to_search, topdown=False, onerror=handle_error):
            for name in files:
                add_file(root, name)

    logger.info('%d files have been found; %d inaccessible paths skipped', len(ret_list), skipped)
    return ret_list


def with_path_prefix(files, source_directory, prefix):
    """Replace the local mount path in CSV rows, retaining relative folders."""
    from pathlib import Path
    source = Path(source_directory)
    result = []
    for row in files:
        exported = list(row)
        relative = Path(row[1]).relative_to(source)
        exported[1] = str(Path(prefix) / relative)
        result.append(exported)
    return result


def copy_files(files, source_directory, destination):
    """Copy a listing, preserving subfolders and refusing existing destinations."""
    import shutil
    from pathlib import Path
    source = Path(source_directory).resolve()
    destination = Path(destination).resolve()
    if destination == source or source in destination.parents:
        raise ValueError('Choose a destination outside the source directory')
    plan = []
    for row in files:
        original = Path(row[1]) / row[0]
        # Reject links escaping the selected root, including links changed after Find.
        original.resolve().relative_to(source)
        target = destination / original.relative_to(source)
        target.parent.resolve().relative_to(destination)
        if target.exists() or target.is_symlink():
            raise FileExistsError(f'Destination already exists: {target}')
        plan.append((original, target))
    copied = 0
    for original, target in plan:
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with original.open('rb') as src, target.open('xb') as dst:
                try:
                    shutil.copyfileobj(src, dst)
                except BaseException:
                    target.unlink()
                    raise
            shutil.copystat(original, target)
        except OSError as error:
            raise OSError(f'Copy stopped after {copied} files: {error}') from error
        copied += 1
    return copied


# write the output
def write_cvs(_files, _output_file):
    # encoding should be utf-8,
    encoding = 'utf-8'
    # but this tool is made for windows mainly in
    # french language -> iso 8859-15
    if 'windows' in platform.system().lower():
        encoding = 'CP1252'
    import csv
    with open(_output_file, 'w', encoding=encoding, errors='strict', newline='') as fout:
        writer = csv.writer(fout, delimiter=';', lineterminator='\n')
        writer.writerow(columns)
        writer.writerows(_files)


if __name__ == '__main__':
    import sys
    if len(sys.argv) != 3:
        print('Wrong arguments, please specify a directory and a name')
        exit(-1)

    input_dir = sys.argv[1]
    name = sys.argv[2]

    files = find_files(input_dir, name, False)
    write_cvs(files, 'result.csv')
