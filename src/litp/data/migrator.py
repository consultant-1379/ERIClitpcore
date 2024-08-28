# pylint: disable=missing-docstring
import argparse
import json
import logging
import logging.config
import os
import sys

import cherrypy

import litp.data.constants as data_constants
import litp.core.constants as core_constants

from litp.core.litp_logging import LitpLogger

from litp.core.model_container import ModelItemContainer

from litp.core.nextgen.execution_manager import ExecutionManager
from litp.core.nextgen.model_manager import ModelManager
from litp.core.nextgen.plugin_manager import PluginManager
from litp.core.nextgen.puppet_manager import PuppetManager

from litp.data.data_manager import DataManager
from litp.data.db_storage import DbStorage
from litp.data.dbapi_wrapper import dbapi_context
from litp.data.dbop import do_check

from litp.data.exceptions import (
    MigrationException,
    NoLegacyStoreException,
    LegacyStoreExistsException)

log = LitpLogger()

C_MIGRATE = 'migrate'
C_CHECK_MIGRATE = 'check_migrate'


class Migrator(object):
    def __init__(self, data_manager, model_manager, plugin_manager, config):
        self._data_manager = data_manager
        self._model_manager = model_manager
        self._plugin_manager = plugin_manager

        self._base_path = config["dbase_root"]
        self._last_known_config_name = config["dbase_last_known_link"]
        # pylint: disable=invalid-name
        self._last_successful_plan_model_name = \
            config["last_successful_plan_model"]
        self._snapshot_plan_prefix = "SNAPSHOT_PLAN_"

    def _deserialize(self, model_type, source_file):
        if model_type == core_constants.LIVE_MODEL:
            model_id = data_constants.LIVE_MODEL_ID
        elif model_type == core_constants.LAST_SUCCESSFUL_PLAN_MODEL:
            model_id = data_constants.LAST_SUCCESSFUL_PLAN_MODEL_ID
        elif model_type == core_constants.SNAPSHOT_PLAN_MODEL:
            filename = source_file.name.rsplit("/", 1)[-1]
            model_id = data_constants.SNAPSHOT_PLAN_MODEL_ID_PREFIX + \
                filename[len(self._snapshot_plan_prefix):]
        else:
            raise NotImplementedError("unknown model type: %s" % model_type)

        data_manager = DataManager(self._data_manager.session)
        data_manager.configure(self._model_manager, model_id=model_id)

        if model_id == data_constants.LIVE_MODEL_ID:
            puppet_manager = PuppetManager(None)
            puppet_manager.data_manager = data_manager

            execution_manager = ExecutionManager(None, puppet_manager, None)
            execution_manager.data_manager = data_manager
        else:
            execution_manager = None

        self._model_manager.data_manager = data_manager
        try:
            container = ModelItemContainer(
                self._model_manager, self._plugin_manager, execution_manager)
            container.do_unpickling(json.load(source_file), model_type)
        finally:
            self._model_manager.data_manager = None

    def _get_path_for_filename(self, filename):
        return os.path.join(self._base_path, filename)

    def _migrate_file(self, model_type, path):
        log.event.info(
            "JSON files: migrating file: %s; model_type: %s" % (
                path, model_type))
        with open(path, "r") as source_file:
            self._deserialize(model_type, source_file)

    def _migrate_file_if_exists(self, model_type, name):
        path = self._get_path_for_filename(name)
        if os.path.exists(path):
            self._migrate_file(model_type, path)

    def is_migration_required(self):
        path = self._get_path_for_filename(self._last_known_config_name)
        return os.path.exists(path)

    def cleanup(self):
        target_path = "%s.db.bak" % os.path.normpath(self._base_path)
        log.event.info(
            "JSON files: archiving files in %s to %s" % (
                self._base_path, target_path))
        os.rename(self._base_path, target_path)

    def migrate(self):
        if not os.path.exists(self._base_path):
            return
        self._migrate_file_if_exists(
            core_constants.LIVE_MODEL,
            self._last_known_config_name)
        self._migrate_file_if_exists(
            core_constants.LAST_SUCCESSFUL_PLAN_MODEL,
            self._last_successful_plan_model_name)
        for name in os.listdir(self._base_path):
            if not name.startswith(self._snapshot_plan_prefix):
                continue
            self._migrate_file(
                core_constants.SNAPSHOT_PLAN_MODEL,
                os.path.join(self._base_path, name))


def do_migrate(context):
    """
    Migrate legacy JSON data to DB.
    JSON files will be deleted on completion.
    Checks for schema being up-to-date.
    """
    log.event.info("JSON files: Migrating data in JSON files to DB")
    do_check(context)
    connection, cherrypy_config = context.connection, context.cherrypy_config
    litp_root = cherrypy_config.get("litp_root", "/opt/ericsson/nms/litp")
    model_manager = ModelManager()
    plugin_manager = PluginManager(model_manager)
    plugin_manager.add_extensions(os.path.join(
        litp_root, 'etc/extensions/'))
    plugin_manager.add_plugins(os.path.join(
        litp_root, 'etc/plugins/'))

    db_storage = DbStorage(connection)
    data_manager = DataManager(db_storage.create_session())
    migrator = Migrator(
        data_manager,
        model_manager,
        plugin_manager,
        cherrypy_config)
    if migrator.is_migration_required():
        try:
            migrator.migrate()
            data_manager.commit()
            migrator.cleanup()
            log.event.info("JSON files: Migrated data in JSON files to DB")
        except:
            data_manager.rollback()
            raise
    else:
        log.event.error("JSON files: Not found")
        raise NoLegacyStoreException("No JSON files")


def do_migrate_check(config):
    """Check if legacy JSON data is present."""
    # No real point hitting the DB here.
    log.event.info("JSON files: Checking for JSON files")
    base_path = config["dbase_root"]
    last_known_config_name = config["dbase_last_known_link"]
    path = os.path.join(base_path, last_known_config_name)
    if os.path.exists(path):
        log.event.info("JSON files: Found")
        raise LegacyStoreExistsException("Found JSON files")
    log.event.info("JSON files: Not found")


def main():
    try:
        parser = argparse.ArgumentParser(
            description='JSON data to DB migrator')
        parser.add_argument(
            '--action', type=str,
            choices=[C_MIGRATE, C_CHECK_MIGRATE],
            help='Action to perform: migrate or check_migrate.')
        parser.add_argument(
            '-c', '--config-file', type=str,
            default='/etc/litpd.conf',
            help='Specify config file, default /etc/litpd.conf')
        parser.add_argument(
            '-l', '--logging-conf', type=str,
            default="/etc/litp_logging.conf",
            help='logging conf, default /etc/litp_logging.conf')
        args = parser.parse_args()
        logging.config.fileConfig(args.logging_conf)
    except Exception as e:  # pylint: disable=broad-except
        message = "JSON files: Error during initialisation: %s" % (e,)
        sys.stderr.write("\n" + message + "\n")
        log.event.exception(message)
        return 1

    try:
        if args.action == C_MIGRATE:
            with dbapi_context(args.config_file) as context:
                do_migrate(context)

        elif args.action == C_CHECK_MIGRATE:
            cherrypy.config.update(args.config_file)
            try:
                do_migrate_check(cherrypy.config)
            except LegacyStoreExistsException as lsee:
                return lsee.exit_code

        else:
            raise NotImplementedError("unknown action: %s" % args.action)

    except MigrationException as me:
        message = "JSON files: Error performing operation: %s" % (me,)
        sys.stderr.write("\n" + message + "\n")
        log.event.error(message)
        return me.exit_code
    except Exception as e:  # pylint: disable=broad-except
        message = ("JSON files: Unexpected error performing operation: %s" %
            (e,))
        sys.stderr.write("\n" + message + "\n")
        log.event.exception(message)
        return 1

    return 0

if __name__ == '__main__':
    sys.exit(main())
