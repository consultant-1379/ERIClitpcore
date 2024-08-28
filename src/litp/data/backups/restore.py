import os
import subprocess
import tarfile
import platform

from contextlib import closing

import cherrypy

from litp.data.backups.common import get_manifest_dir, get_db_credentials
from litp.data.backups.constants import (
    PGRESTORE, LITP_DUMP, BACKUPS_FORMAT_VERSION_PATH)
from litp.data.backups.exceptions import (
    PgRestoreException, OldFashionedBackupException,
    BackupIncompleteDumpMissingException
)


def restore_manifests(tarball, manifests):
    for member in manifests:
        tarball.extract(member, path='/')


def restore_litp_db(tarball, dump, db_name):
    cmd = "su - postgres -c 'PGSSLMODE=verify-full {0} -h {1} -d {2} -c'" \
        .format(PGRESTORE, platform.node(), db_name)
    proc = subprocess.Popen(
        cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stdin=subprocess.PIPE
    )
    with closing(tarball.extractfile(dump)) as dump_file:
        stdout, stderr = proc.communicate(dump_file.read())
        if proc.returncode != 0:
            raise PgRestoreException(proc.returncode, stdout, stderr)


def do_restore(cli_args):
    cherrypy.config.update(cli_args.config_file)
    manifests_prefix = get_manifest_dir(cherrypy.config).lstrip(os.sep)
    # pylint: disable=unused-variable
    db_name, _db_user = get_db_credentials(cherrypy.config)
    with closing(tarfile.open(cli_args.backup_file, 'r:gz')) as tarball:
        manifests = []
        binary_dump_found = False
        backups_version = '0'

        for member in tarball.getmembers():
            name = member.name

            if name.startswith(manifests_prefix):
                manifests.append(member)
            elif name == LITP_DUMP:
                binary_dump_found = True
            elif name.startswith(BACKUPS_FORMAT_VERSION_PATH):
                backups_version = os.path.basename(name)

        if '0' == backups_version:
            raise OldFashionedBackupException(cli_args.backup_file)
        elif '1' == backups_version:
            if not binary_dump_found:
                raise BackupIncompleteDumpMissingException(
                    cli_args.backup_file)

        restore_manifests(tarball, manifests)
        dump = tarball.getmember(LITP_DUMP)
        restore_litp_db(tarball, dump, db_name)
