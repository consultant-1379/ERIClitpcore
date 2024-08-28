# pylint: disable=missing-docstring
import argparse
import logging
import logging.config
import os
import sys

from sqlalchemy import Table
from sqlalchemy.orm import Session

# importing for side-effect
# pylint: disable=unused-import
from litp.core.persisted_task import PersistedTask
from litp.core.extension_info import ExtensionInfo
from litp.core.plan import BasePlan
from litp.core.plugin_info import PluginInfo
from litp.core.plan_task import PlanTask
from litp.core.model_item import ModelItem
from litp.core.task import Task
from litp.data.global_options import GlobalOption
from litp.data.passwd_history import PasswordHistory

from litp.core import scope
from litp.core.litp_logging import LitpLogger

from litp.core.nextgen.model_manager import ModelManager
from litp.core.nextgen.plugin_manager import PluginManager

from litp.data.dbapi_wrapper import dbapi_context

from litp.data.data_manager import DataManager
from litp.data.db_storage import DbStorage, get_engine
from litp.data.types.base import Base
from litp.data.db_version import ensure_record_exists

from litp.data.exceptions import (
    MigrationException,
    NothingAppliedException,
    UpgradeRequiredException,
    NoModelException,
    ModelExistsException)

log = LitpLogger()

C_UPGRADE = 'upgrade'
C_CHECK = 'check_pending'
C_PURGE = 'purge'
C_CHECK_MODEL = 'check_model'
C_DEFAULT_MODEL = 'default_model'


def do_upgrade(context):
    """ Upgrade database schema """
    log.event.info("DB: Performing upgrade")
    dbapi = context.dbapi
    connection = context.connection
    if len(dbapi.current()):
        log.event.info("DB: Existing DB found, upgrading")
        # something in db already -> run migrations
        dbapi.upgrade('head')
    else:
        log.event.info("DB: Empty DB found, initialising")
        # fresh db -> create all and stamp
        # checkfirst=False guarantees existing tables with
        # names used by the schema won't be tolerated
        # reuse connection stay in the same transaction
        Base.metadata.create_all(connection, checkfirst=False)
        dbapi.stamp('head')
    # it really should go to data migrations but we value "warp" upgrade path
    # pylint: disable=invalid-name
    session = Session(bind=connection)
    ensure_record_exists(session)
    session.close()
    log.event.info("DB: Performed upgrade")


def do_purge(context):
    """ Purge database """
    log.event.info("DB: Performing purge")
    dbapi = context.dbapi
    connection = context.connection
    _ = Table('alembic_version', Base.metadata)
    # checkfirst=True ignores missing tables in case of purging of partial db
    Base.metadata.drop_all(connection, checkfirst=True)
    log.event.info("DB: Performed purge")


def do_check(context):
    """ Check pending migrations """
    log.event.info("DB: Checking DB schema")
    dbapi = context.dbapi
    currents = dbapi.current()
    if len(currents) == 0:
        log.event.info("DB: Nothing Applied")
        raise NothingAppliedException("Nothing Applied")
    # the current must be the head
    if currents[0] != dbapi.heads()[0]:
        log.event.info("DB: Upgrade Required")
        raise UpgradeRequiredException("Upgrade Required")


def do_check_model(context):
    """
    Checks if a litp model exists in the database

    Checks for schema being up-to-date.
    """
    log.event.info("DB: Checking LITP model")
    do_check(context)
    connection, cherrypy_config = context.connection, context.cherrypy_config
    litp_root = cherrypy_config.get("litp_root", "/opt/ericsson/nms/litp")
    model_manager = ModelManager()
    plugin_manager = PluginManager(model_manager)
    plugin_manager.add_extensions(os.path.join(
        litp_root, 'etc/extensions/'))
    plugin_manager.add_plugins(os.path.join(
        litp_root, 'etc/plugins/'))

    engine = get_engine(cherrypy_config)
    db_storage = DbStorage(engine)

    session = db_storage.create_session()
    data_manager = DataManager(session)
    data_manager.configure(model_manager)
    scope.data_manager = data_manager
    try:
        if not data_manager.model.exists("/"):
            log.event.info("DB: No LITP model")
            raise NoModelException("No Model")
        db_storage.close()
        data_manager.close()
        log.event.info("DB: LITP model found")
    except:
        data_manager.rollback()
        raise


def do_default_model(context):
    """
    Create the empty default litp model

    Checks for schema being up-to-date.
    """
    log.event.info("DB: Creating default LITP model")
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
    data_manager.configure(model_manager)
    scope.data_manager = data_manager
    try:
        if not data_manager.model.exists("/"):
            plugin_manager.add_default_model()
        else:
            raise ModelExistsException("Model Exists")
        data_manager.commit()
        log.event.info("DB: Default LITP model created")
    except:
        data_manager.rollback()
        raise


def main():
    try:
        parser = argparse.ArgumentParser(description='LITP DB Alembic tasks')
        parser.add_argument(
            '--action', type=str,
            choices=[
                C_UPGRADE,
                C_CHECK,
                C_CHECK_MODEL,
                C_PURGE,
                C_DEFAULT_MODEL],
            help='Action to perform.')
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
        message = "DB: Error during initialisation: %s" % (e,)
        sys.stderr.write("\n" + message + "\n")
        log.event.exception(message)
        return 1

    try:
        log.set_log_name("LITP DB op: {0}".format(args.action))
        if args.action == C_UPGRADE:
            with dbapi_context(args.config_file) as context:
                do_upgrade(context)

        elif args.action == C_CHECK:
            try:
                with dbapi_context(args.config_file) as context:
                    do_check(context)
            except NothingAppliedException as nae:
                return nae.exit_code
            except UpgradeRequiredException as ure:
                return ure.exit_code

        elif args.action == C_CHECK_MODEL:
            try:
                with dbapi_context(args.config_file) as context:
                    do_check_model(context)
            except NoModelException as nme:
                return nme.exit_code

        elif args.action == C_DEFAULT_MODEL:
            with dbapi_context(args.config_file) as context:
                do_default_model(context)

        elif args.action == C_PURGE:
            with dbapi_context(args.config_file) as context:
                do_purge(context)

        else:
            raise NotImplementedError("unknown action: %s" % args.action)

    except MigrationException as me:
        message = "DB: Error performing operation: %s" % (me,)
        sys.stderr.write("\n" + message + "\n")
        log.event.error(message)
        return me.exit_code
    except Exception as e:  # pylint: disable=broad-except
        message = "DB: Unexpected error performing operation: %s" % (e,)
        sys.stderr.write("\n" + message + "\n")
        log.event.exception(message)
        return 1

    return 0

if __name__ == '__main__':
    sys.exit(main())
