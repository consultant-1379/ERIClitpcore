import os
import imp

from litp.migration.utils import normalize_version
from litp.core.litp_logging import LitpLogger
from litp.data.constants import SNAPSHOT_PLAN_MODEL_ID_PREFIX


log = LitpLogger()


def import_from_path(module_name, path):
    """
    Import a module from source path

    """
    try:
        module = imp.load_source(module_name, path)
    except IOError:
        return None
    return module


class Migrator(object):

    def __init__(self, litp_root, model_manager, plugin_manager):
        self.litp_root = litp_root
        self.model_manager = model_manager
        self.plugin_manager = plugin_manager
        self.current_extensions = self.get_persisted_extensions()
        self.new_extensions = self.get_installed_extensions()
        self.migrations = {}

    @property
    def data_manager(self):
        return self.model_manager.data_manager

    def get_persisted_extensions(self):
        current_extensions = {}
        extensions = self.data_manager.get_extensions()
        for extension in extensions:
            current_extensions[extension.name] = {
                "classpath": extension.classpath,
                "version": normalize_version(extension.version)
            }
        if not len(current_extensions):
            current_extensions = self.get_installed_extensions()
        return current_extensions

    def get_installed_extensions(self):
        new_extensions = {}
        ext_conf_dir = os.path.join(self.litp_root, 'etc/extensions/')
        for name, classpath, version in \
            self.plugin_manager.read_ext_config(ext_conf_dir):
            new_extensions[name] = {
                "classpath": classpath,
                "version": normalize_version(version)
            }
        return new_extensions

    def _get_migrations_path(self, extension_name):
        return os.path.join(self.litp_root, 'etc/migrations',
                            extension_name, '__init__.py')

    def load_migrations(self):
        self.migrations = {}
        for ext_name in self.new_extensions.keys():
            module = import_from_path(ext_name,
                                      self._get_migrations_path(ext_name))
            if module:
                directory = os.path.abspath(os.path.dirname(module.__file__))

                for name in os.listdir(directory):
                    if name.endswith(".py") and not name.endswith("__.py"):
                        migration_name = name.rsplit(".", 1)[0]
                        migration_path = os.path.join(directory, name)
                        try:
                            migration_module = import_from_path(migration_name,
                                                            migration_path)
                            if hasattr(migration_module, "Migration"):
                                self.migrations.setdefault(
                                    ext_name, []
                                ).append(migration_module.Migration())
                        except Exception, e:
                            log.trace.error(
                                "error instantiating migration:"
                                " '%s' error: <%s>" % (migration_path, e))
                            raise e

    def get_new_version_for_ext(self, extension_name):
        version = None
        if extension_name in self.new_extensions:
            version = self.new_extensions[extension_name]["version"]
        return version

    def get_current_version_for_ext(self, extension_name):
        version = None
        if extension_name in self.current_extensions:
            version = self.current_extensions[extension_name]["version"]
        return version

    def get_restore_model_extension_version(self, ext_name):
        """Get the extension version at the time the restore point was taken.

        If the extension cannot be found (e.g. added post restore point),
        then return the current LIVE version, so no migration is applied.
        """
        extension = self.data_manager.get_restore_model_extension(ext_name)
        if extension is not None:
            return normalize_version(extension.version)
        return self.get_current_version_for_ext(ext_name)

    @staticmethod
    def migration_required(from_version, to_version, migration_version):
        direction = None
        if from_version is None or to_version is None:
            direction = None
        elif from_version < migration_version <= to_version:
            direction = "forwards"
        elif to_version < migration_version <= from_version:
            direction = "backwards"
        return direction

    def apply_migrations(self, restore_model=False):
        try:
            self._apply_migrations(restore_model)
        except Exception, e:
            self.data_manager.rollback()
            raise e
        self.data_manager.commit()

    def _apply_migrations(self, restore_model):
        direction_sort_map = {'forwards': sorted, 'backwards': reversed}
        to_apply = {}
        self.load_migrations()
        log.trace.debug("loaded migrations: '%s'" % (self.migrations))
        for ext_name, migrations in self.migrations.items():
            new_version = self.get_new_version_for_ext(ext_name)
            if restore_model:
                current_version = self.get_restore_model_extension_version(
                    ext_name)
            else:
                current_version = self.get_current_version_for_ext(ext_name)
            for migration in migrations:
                direction = self.migration_required(
                    current_version, new_version, migration.normalized_version)
                if direction is not None:
                    migration_list = to_apply.get(direction, [])
                    migration_list.append(migration)
                    to_apply[direction] = migration_list

        for direction, migration_list in to_apply.iteritems():
            sort_func = direction_sort_map[direction]
            log.trace.info("%s migrations to_apply: '%s'" % (direction,
                                                             migration_list))
            for migration in sort_func(migration_list):
                log.trace.debug("applying migration: '%s'" % (migration))
                try:
                    getattr(migration, direction)(self.model_manager)
                except Exception, e:
                    log.trace.error(
                        "error applying migration: '%s' with error: <%s>" %
                        (migration, e), exc_info=True)
                    raise e

        self._upgrade_backup_snapshots()

    def _upgrade_backup_snapshots(self):
        snapshots = self.model_manager.query("snapshot-base")
        for snapshot in snapshots:
            if not self.data_manager.model.backup_exists(
                        SNAPSHOT_PLAN_MODEL_ID_PREFIX + snapshot.item_id
                    ):
                self.data_manager.model.create_backup(snapshot.item_id)
