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
        filename.replace(';', '-'),
        _parent_directory,
        filename.split('.')[-1],
        '%.2f Mo' % (_size/megabyte),
        _location_label,
    ])

# find the files


def find_files(_dir_to_search, _location_label, _simpleSearch=True):
    import os
    ret_list = []

    # directory might be given with / instead of \\
    # so we normalize it all
    logger.debug('raw input directory : %s' % _dir_to_search)
    dir_to_search = os.path.abspath(_dir_to_search)
    logger.info('The directory to explore: %s' % dir_to_search)

    if _simpleSearch:
        # if simple search : just the files in the specified dir
        logger.info('Simple search has been activated')
        for name in os.listdir(dir_to_search):
            full_filename = os.path.join(dir_to_search, name)
            if os.path.isfile(full_filename):
                size = os.stat(full_filename).st_size
                add_file_to_list(ret_list, name, dir_to_search,
                                 size, _location_label)

    else:
        # recursive searche
        for root, dirs, files in os.walk(dir_to_search, topdown=False):
            for name in files:
                full_filename = os.path.join(root, name)
                size = os.stat(full_filename).st_size
                add_file_to_list(ret_list, name, root, size, _location_label)

    logger.info('%d files have been found' % (len(ret_list)))
    return ret_list


# write the output
def write_cvs(_files, _output_file):
    # encoding should be utf-8,
    encoding = 'utf-8'
    # but this tool is made for windows mainly in
    # french language -> iso 8859-15
    if 'windows' in platform.system().lower():
        encoding = 'CP1252'
    with open(_output_file, 'w', encoding=encoding, errors='ignore') as fout:
        logger.info("writing file {}".format(_output_file))
        str_columns = ';'.join(columns)+'\n'
        fout.write(str_columns)
        for fil in _files:
            str_to_write = ';'.join(fil)+'\n'
            fout.write(str_to_write)


if __name__ == '__main__':
    import sys
    if len(sys.argv) != 3:
        print('Wrong arguments, please specify a directory and a name')
        exit(-1)

    input_dir = sys.argv[1]
    name = sys.argv[2]

    files = find_files(input_dir, name, False)
    write_cvs(files, 'result.csv')
