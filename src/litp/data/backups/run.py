import os
import sys


from litp.data.backups.exceptions import (
    PermissionException, BackupException, NotRequiredException)
from litp.data.backups.parsers import get_argparser


def main():
    try:
        if os.getuid():
            raise PermissionException

        arg_parser = get_argparser()
        cli_args = arg_parser.parse_args()
        cli_args.func(cli_args)
    except NotRequiredException as nre:
        return nre.errno
    except BackupException as exc:
        print >>sys.stderr, str(exc)
        return exc.errno
    except Exception as exc:
        print >>sys.stderr, str(exc)
        return 1
    else:
        return 0


if '__main__' == __name__:
    sys.exit(main())
