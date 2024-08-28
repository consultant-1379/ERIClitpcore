import datetime
import glob
import os
import subprocess
import tarfile
import time
import zlib
import sys
import platform

from cStringIO import StringIO
from contextlib import closing

import cherrypy

from litp.data.backups.common import get_manifest_dir, get_db_credentials
from litp.data.backups.constants import (
    BACKUP_PREFIX, TIMESTAMP_GLOB, PGDUMP, TIMESTAMP_FORMAT, LITP_DUMP,
    MAX_BACKUPS, BACKUPS_CURRENT_VERSION_PATH,
    BACKUPS_DB_HASH_PATH)
from litp.data.backups.exceptions import (
    MissingDirectoryException, NotRequiredException, PgDumpException,
    BinaryException)
from litp.data.global_options import GlobalOption
from litp.data.db_version import GLOBAL_ID
from litp.data.data_manager import DataManager
from litp.data.db_storage import DbStorage, get_engine


def get_size(open_file):
    open_file.seek(0, os.SEEK_END)
    size = open_file.tell()
    open_file.seek(0, os.SEEK_SET)
    return size


def checked_directory(directory, is_executable=False, is_writable=False):
    result = os.path.realpath(directory)
    flags = os.R_OK
    if is_executable:
        flags = flags | os.X_OK
    if is_writable:
        flags = flags | os.W_OK
    if not (os.path.isdir(result) and os.access(result, flags)):
        raise MissingDirectoryException(result)
    return result


def get_backup_name(timestamp):
    return BACKUP_PREFIX + timestamp + '.tar.gz'


def list_backups(output_dir):
    backup_glob = os.path.join(output_dir, get_backup_name(TIMESTAMP_GLOB))
    backups = glob.glob(backup_glob)
    backups.sort()
    return backups


def get_db_version_stamp(config):
    """
    There is always exactly one row.
    In the beginning get inserted by data migration.
    """
    engine = get_engine(config)
    storage = DbStorage(engine)
    session = storage.create_session()
    data_manager = DataManager(session)
    version = session.query(GlobalOption).filter_by(id=GLOBAL_ID).first()
    if version is None:
        result = None
    else:
        result = str(version.value)
    storage.close()
    data_manager.close()
    return result


def do_backup(cli_args):
    cherrypy.config.update(cli_args.config_file)
    output_dir = checked_directory(cli_args.output_dir, is_writable=True)
    backups = list_backups(output_dir)
    db_stamp = get_db_version_stamp(cherrypy.config)
    if is_plan_running() or not is_backup_needed(db_stamp, backups):
        raise NotRequiredException
    # pylint: disable=unpacking-non-sequence
    create_backup(output_dir, cherrypy.config, db_stamp)
    remove_oldest_backups(backups)


def get_datetime_now():
    return datetime.datetime.utcnow()


def dump_litp_db(config):
    db_name, db_user = get_db_credentials(config)
    try:
        env = os.environ.copy()
        env['PGSSLMODE'] = 'verify-full'
        proc = subprocess.Popen(
            [PGDUMP, '-Fc', '-c', '-U', db_user,
             '-h', platform.node(), db_name],
            stdout=subprocess.PIPE,
            env=env
        )

    except OSError:
        raise BinaryException(PGDUMP)
    stdout, stderr = proc.communicate()
    if proc.returncode != 0:
        raise PgDumpException(proc.returncode, stdout, stderr)
    return StringIO(stdout)


def create_backup(outdir, config, db_stamp_hash):
    timestamp = get_datetime_now().strftime(TIMESTAMP_FORMAT)
    backup_name = get_backup_name(timestamp)
    outfile = os.path.join(outdir, backup_name)
    manifest_glob = os.path.join(get_manifest_dir(config), '*.pp')
    manifests = glob.glob(manifest_glob)

    print "Creating {0}".format(outfile)
    try:
        with closing(tarfile.open(outfile, 'w:gz')) as tarball:
            # Back up the Puppet manifests
            for pathname in manifests:
                tarball.add(pathname)
                # Back up the LITP database
            posix_now = int(time.time())
            with closing(dump_litp_db(config)) as dump_file:
                dump_tar_member = tarfile.TarInfo(name=LITP_DUMP)
                dump_tar_member.mtime = posix_now
                dump_tar_member.size = get_size(dump_file)
                tarball.addfile(dump_tar_member, fileobj=dump_file)
                # Add db hash
            db_hash_path = os.path.join(BACKUPS_DB_HASH_PATH, db_stamp_hash)
            hash_member = tarfile.TarInfo(name=db_hash_path)
            hash_member.mtime = posix_now
            tarball.addfile(hash_member)
            # Add backups version
            current_version_member = tarfile.TarInfo(
                name=BACKUPS_CURRENT_VERSION_PATH)
            current_version_member.mtime = posix_now
            tarball.addfile(current_version_member)
    except Exception as exc:
        if os.path.isfile(outfile):
            print "Removing {0}".format(outfile)
            os.unlink(outfile)
        raise exc


def get_backup_version_stamp(backup):
    try:
        with closing(tarfile.open(backup, 'r:gz')) as tarball:
            for name in tarball.getnames():
                if name.startswith(BACKUPS_DB_HASH_PATH):
                    return os.path.basename(name)
    except (IOError, tarfile.TarError, zlib.error) as e:
        print >> sys.stderr, "Invalid backup {0}, " \
                             "version stamp is not available" \
            .format(backup)
        print >> sys.stderr, e.message
        return "no-backup-timestamp-available"


def is_backup_needed(db_stamp, backups):
    if db_stamp is None:
        return False
    if len(backups) == 0:
        return True
    last_backup = backups[-1]
    backup_stamp = get_backup_version_stamp(last_backup)
    return db_stamp != backup_stamp


def is_plan_running():
    cmd = "litp show -p /plans/plan 2>&1 | grep 'state: running'"
    return subprocess.call(cmd, shell=True, stdout=subprocess.PIPE) == 0


def remove_oldest_backups(backups):
    outdated_backups = backups[:-(MAX_BACKUPS - 1)]
    for pathname in outdated_backups:
        os.remove(pathname)
