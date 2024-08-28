# Prefix used in naming backup tarballs
BACKUP_PREFIX = 'litp_backup_'

# This matches the filename of backup tarballs created by this script.
# example filename: litp_backup_20160209184904.tar.gz
# (Compatible with "egrep" and "sed -r")
DEFAULT_CONFIG = '/etc/litpd.conf'
MANIFEST_DIR = 'etc/puppet/manifests/plugins'
PGDUMP = '/usr/bin/pg_dump'
PGRESTORE = '/usr/bin/pg_restore'

LITP_DUMP = 'litp_db.dump'

MAX_BACKUPS = 5

TIMESTAMP_GLOB = "[0-9]" * 14
TIMESTAMP_FORMAT = '%Y%m%d%H%M%S'
DEFAULT_LITP_ROOT = "/opt/ericsson/nms/litp"

BACKUPS_VERSION = '1'
BACKUPS_FORMAT_VERSION_PATH = 'META-INF/LITP_BACKUP_FORMAT_VERSION'
BACKUPS_CURRENT_VERSION_PATH = (
    BACKUPS_FORMAT_VERSION_PATH + '/' + BACKUPS_VERSION)
BACKUPS_DB_HASH_PATH = 'META-INF/DB_HASH'
