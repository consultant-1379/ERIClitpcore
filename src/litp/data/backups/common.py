import os
import urlparse

from litp.data.backups.constants import DEFAULT_LITP_ROOT, MANIFEST_DIR


def get_db_credentials(config):
    split_db_url = urlparse.urlsplit(config['sqlalchemy.url'])
    return (split_db_url.path[1:],
            split_db_url.username)


def get_manifest_dir(config):
    litp_root = config.get("litp_root", DEFAULT_LITP_ROOT)
    return os.path.join(litp_root, MANIFEST_DIR)
