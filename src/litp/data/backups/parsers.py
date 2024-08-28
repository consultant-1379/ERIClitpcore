import argparse

from litp.data.backups.constants import DEFAULT_CONFIG
from litp.data.backups.backup import do_backup
from litp.data.backups.restore import do_restore


def get_argparser():
    arg_parser = argparse.ArgumentParser(
        description='LITP State Backup/Restore tool'
    )
    arg_parser.add_argument(
        '-c', '--config-file', type=str,
        default=DEFAULT_CONFIG,
        help='Specify config file, default ' + DEFAULT_CONFIG
    )
    subparsers = arg_parser.add_subparsers()

    backup_arg_parser = subparsers.add_parser('backup')
    backup_arg_parser.add_argument(
        'output_dir', type=str,
        help='Directory in which the backup tarball will be created'
    )
    backup_arg_parser.set_defaults(func=do_backup)

    restore_arg_parser = subparsers.add_parser('restore')
    restore_arg_parser.add_argument(
        'backup_file', type=str,
        help='The backup tarball to be restored'
    )
    restore_arg_parser.set_defaults(func=do_restore)

    return arg_parser
