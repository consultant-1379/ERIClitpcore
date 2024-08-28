import logging
import logging.config
import logging.handlers
import os
import argparse
import cherrypy
import platform
import sys
import shutil
import time
import datetime
from grp import getgrnam
from pwd import getpwnam

from litp.core.constants import CELERY_USER, CELERY_GROUP
import litp.metrics
from litp.data.db_storage import DbStorage, get_engine
from litp.data.data_manager import DataManager
from litp.core.extension_info import ExtensionInfo
from litp.core.plugin_info import PluginInfo
from litp.core.password_history_info import PasswordHistoryInfo
from litp.service.cherrypy_server import CherrypyServer
from litp.core import scope
from litp.core.nextgen.model_manager import ModelManager
from litp.core.nextgen.execution_manager import ExecutionManager
from litp.core.nextgen.plugin_manager import PluginManager
from litp.core.nextgen.puppet_manager import PuppetManager
from litp.core.litp_logging import LitpLogger, OwnedWatchedFileHandler
from litp.core.exceptions import ModelItemContainerException
from litp.core.exceptions import DataIntegrityException
from litp.core.callback_api import CallbackApi
from litp.core.schemawriter import SchemaWriter
from litp.core.maintenance import initialize_maintenance
from litp.core.config_validator import ConfigValidator
from litp.core.worker.celery_app import celery_app, CELERY_DEFAULTS
from litp.xml.xml_loader import XmlLoader
from litp.xml.xml_exporter import XmlExporter
from litp.migration.migrator import Migrator
from lxml.etree import XMLSchemaParseError


log = LitpLogger()


def generate_xml_schema():
    litp_path = cherrypy.config.get("litp_root")
    schema_path = os.path.join(litp_path, "share", "xsd")
    shutil.rmtree(schema_path, True)
    os.makedirs(schema_path)
    basepaths = [os.path.join(litp_path, "etc/plugins"),
        os.path.join(litp_path, "etc/extensions")]
    writer = SchemaWriter(schema_path, basepaths)
    writer.write()
    return schema_path


def check_plugins(data_manager, plugin_manager):
    installed_plugins = set([
        plugin["name"] for plugin in plugin_manager.get_plugin_info()])
    saved_plugins = set([
        plugin_info.name for plugin_info in data_manager.get_plugins()])
    removed_plugins = saved_plugins.difference(installed_plugins)
    for plugin in removed_plugins:
        log.trace.info("Removed Plugin: \"%s\"", plugin)

    installed_extensions = set([
        ext["name"] for ext in plugin_manager.get_extension_info()])
    saved_extensions = set([
        ext_info.name for ext_info in data_manager.get_extensions()])
    removed_extensions = saved_extensions.difference(installed_extensions)
    for extension in removed_extensions:
        log.trace.info("Removed ModelExtension: \"%s\"", extension)


def update_plugins(data_manager, plugin_manager):
    installed_plugins = dict([(plugin["name"], plugin)
        for plugin in plugin_manager.get_plugin_info()])
    saved_plugins = dict([(plugin_info.name, plugin_info)
        for plugin_info in data_manager.get_plugins()])

    for name, plugin in installed_plugins.iteritems():
        if name not in saved_plugins:
            plugin_info = PluginInfo(
                plugin["name"], plugin["class"], plugin["version"])
            data_manager.add_plugin(plugin_info)
        else:
            plugin_info = saved_plugins[name]
            plugin_info.name = plugin["name"]
            plugin_info.classpath = plugin["class"]
            plugin_info.version = plugin["version"]

    for name, plugin_info in saved_plugins.iteritems():
        if name not in installed_plugins:
            data_manager.delete_plugin(plugin_info)

    installed_extensions = dict([(ext["name"], ext)
        for ext in plugin_manager.get_extension_info()])
    saved_extensions = dict([(ext_info.name, ext_info)
        for ext_info in data_manager.get_extensions()])

    for name, ext in installed_extensions.iteritems():
        if name not in saved_extensions:
            ext_info = ExtensionInfo(
                ext["name"], ext["class"], ext["version"])
            data_manager.add_extension(ext_info)
        else:
            ext_info = saved_extensions[name]
            ext_info.name = ext["name"]
            ext_info.classpath = ext["class"]
            ext_info.version = ext["version"]

    for name, ext_info in saved_extensions.iteritems():
        if name not in installed_extensions:
            data_manager.delete_extension(ext_info)


def check_model_item_types(data_manager, model_manager):
    for item_type_id in data_manager.get_model_item_type_ids():
        if item_type_id in model_manager.item_types:
            continue
        raise DataIntegrityException(
            "model contains item with unknown type: \"%s\"" % item_type_id)


def create_litp_items(model_manager):
    model_manager.create_item('logging', '/litp/logging')
    model_manager.create_item('restore', '/litp/restore_model')
    model_manager.create_item('prepare-restore', '/litp/prepare-restore')

    if not model_manager.has_item('/litp/import-iso'):
        model_manager.create_item('import-iso', '/litp/import-iso')

    if model_manager.has_item('/ms'):
        if not model_manager.query('sshd-config'):
            item_path = '/ms/configs/sshd_config'
            if not model_manager.has_item(item_path):
                model_manager.create_item('sshd-config', item_path)
            else:
                for idx in range(1, 100):
                    item_path = '/ms/configs/sshd_config_%02d' % idx
                    if not model_manager.has_item(item_path):
                        model_manager.create_item('sshd-config', item_path)
                        break
        if not model_manager.query('sshd-config'):
            raise DataIntegrityException(
                "failed to create \"sshd-config\" item in \"/ms/configs/\"")

    if not model_manager.has_item('/litp/maintenance'):
        model_manager.create_item('maintenance', '/litp/maintenance')

    initialize_maintenance(model_manager)


def validate_config_file():
    config_errors = ConfigValidator().validate()
    if config_errors:
        message = "Error starting service:\n"
        for error in config_errors:
            message += error + "\n"
        sys.stderr.write(message)
        log.event.error(message)
        sys.exit(1)


def setup_logging(model_manager):
    model_manager.force_debug(force_debug=False, normal_start=True)
    for log_file, logger in [('litpd_access.log', cherrypy.log.access_log),
                             ('litpd_error.log', cherrypy.log.error_log)]:
        try:
            handler = OwnedWatchedFileHandler('/var/log/litp/' + log_file,
                                              getpwnam(CELERY_USER).pw_uid,
                                              getgrnam(CELERY_GROUP).gr_gid)
            handler.setFormatter(cherrypy._cplogging.logfmt)
            logger.addHandler(handler)
        except KeyError as e:
            log.trace.warning("Could not get group id for group {0} "
                              "or user id for user {1}. {2}".
                              format(CELERY_GROUP, CELERY_USER, str(e)))
            raise e


def check_python_and_linux_versions():
    linux_version = platform.dist()
    supported_rhel_versions = ['6.6', '6.10', '7.9']
    if not ((linux_version[0] == 'redhat' or linux_version[0] == 'centos')
        and linux_version[1] in supported_rhel_versions):
        log.trace.warn(("LITP is validated for RedHat versions {0}. "
                       "Your linux is {1}").format(
                       ', '.join(supported_rhel_versions),
                       ' '.join(linux_version)))

    python_version = sys.version_info
    if not (python_version[0] == 2 and \
        (python_version[1] == 6 or python_version[1] == 7)):
        log.trace.warn(
            ("LITP is validated for python 2.6.x and python 2.7.x. "
            "Your version is {0}")
            .format('.'.join(str(v) for v in python_version[0:3])))


def cleanup_model_snapshot_datasets(model_manager, data_manager):
    #Cleanup extraneous snapshot sets - TORF-603745
    valid_snapshots = model_manager.query('snapshot-base')
    data_manager.model.delete_snapshot_sets(valid_snapshots)


def _get_celery_conf():
    conf = {}
    conf.update(CELERY_DEFAULTS)
    if 'celery' in cherrypy.config:
        if 'CELERY_RESULT_BACKEND' in cherrypy.config.get('celery'):
            cherrypy.config['celery']['CELERY_RESULT_BACKEND'] = \
                cherrypy.config['celery']['CELERY_RESULT_BACKEND'] \
                    .replace('\'', '')
        conf.update(cherrypy.config['celery'])
    return conf


def run_service():
    st = time.time()

    if os.getuid():  # Not root
        print "\nPermission denied."
        sys.exit(1)

    litp.metrics.set_handlers()
    service_metrics = litp.metrics.metrics_logger.extend_with('Service')
    startup_metrics = service_metrics.extend_with('Startup')

    def log_startup_time():
        et = time.time()
        tt_metric = {'TimeTaken': '{0:.3f}'.format(et - st)}
        startup_metrics.log(tt_metric)
        cherrypy.engine.unsubscribe(channel='start', callback=log_startup_time)

    cherrypy.engine.subscribe(channel='start', callback=log_startup_time)

    parser = argparse.ArgumentParser(
        description='LITP Deployment Manager Service')
    parser.add_argument('-D', '--daemonize', dest='daemonize',
                        action='store_true', default=False,
                        help='Fork and daemonize the service')
    parser.add_argument('-c', '--config-file', type=str,
                        default='/etc/litpd.conf',
                        help='Specify config file, default /etc/litpd.conf')
    parser.add_argument('-l', '--logging-conf', type=str,
                        default="/etc/litp_logging.conf",
                        help='logging conf, default /etc/litp_logging.conf')
    args = parser.parse_args()
    logging.config.fileConfig(args.logging_conf)
    log.set_log_name("LITP Start-up process")
    check_python_and_linux_versions()
    log.event.info("Starting litpd service")

    try:
        cherrypy.config.update(args.config_file)
        cherrypy.config.update({'engine.autoreload_on': False})
        validate_config_file()

        celery_app.config_from_object(_get_celery_conf(), force=True)

        litp_root = cherrypy.config.get("litp_root", "/opt/ericsson/nms/litp")

        schema_path = generate_xml_schema()

        model_manager = ModelManager()

        plugin_manager = PluginManager(model_manager, daemon=True)
        plugin_manager.add_extensions(os.path.join(
            litp_root, 'etc/extensions/'))
        plugin_manager.add_plugins(os.path.join(
            litp_root, 'etc/plugins/'))

        db_storage = DbStorage(get_engine(cherrypy.config))

        data_manager = DataManager(db_storage.create_session())

        ph_info = PasswordHistoryInfo(user='postgres',
                                 passwd=u'md5958e1c4182a7ba15d80dd107f211e35a',
                                 date=datetime.datetime.now())
        data_manager.add_password_history(ph_info)

        scope.data_manager = data_manager
        data_manager.configure(model_manager)

        puppet_manager = PuppetManager(model_manager, litp_root)
        execution_manager = ExecutionManager(
            model_manager, puppet_manager, plugin_manager)

        cleanup_model_snapshot_datasets(model_manager, data_manager)

        # this is required for the scenario where a created plan exists
        # and plugins are updated before running the plan
        execution_manager.fix_plan_at_service_startup()

        check_plugins(data_manager, plugin_manager)
        check_model_item_types(data_manager, model_manager)

        if not data_manager.model.exists("/"):
            raise DataIntegrityException('No model found.')

        create_litp_items(model_manager)

        migrator = Migrator(litp_root, model_manager, plugin_manager)
        migrator.apply_migrations()
        del migrator

        update_plugins(data_manager, plugin_manager)

        xsd_file = os.path.join(schema_path, "litp.xsd")
        xml_loader = XmlLoader(model_manager, xsd_file)

        CallbackApi(execution_manager).initialize()

        xml_exporter = XmlExporter(model_manager)

        cherrypy.config.update({
            'db_storage': db_storage,
            'model_manager': model_manager,
            'execution_manager': execution_manager,
            'puppet_manager': puppet_manager,
            'xml_loader': xml_loader,
            'xml_exporter': xml_exporter,
        })

        setup_logging(model_manager)
        del scope.data_manager

        data_manager.commit()
        data_manager.close()

        server = CherrypyServer()
        server.start(args.daemonize)

    except (ModelItemContainerException, DataIntegrityException), e:
        message = "Error starting service: %s" % e
        sys.stderr.write("\n" + message + "\n")
        log.event.error(message)
        sys.exit(1)

    except OSError, ose:
        message = "Error starting service: %s" % str(ose)
        sys.stderr.write("\n" + message + "\n")
        log.event.exception(message)
        sys.exit(1)

    except IOError, oe:
        message = "Error starting service: %s" % oe.strerror
        if oe.filename is not None:
            message += " (file: %s)" % oe.filename
        sys.stderr.write("\n" + message + "\n")
        log.event.exception(message)
        sys.exit(1)

    except XMLSchemaParseError, xspe:
        message = "Error starting service: %s" % xspe
        advice = ". Please ensure the system's hostname is not an FQDN"
        sys.stderr.write("\n" + message + advice + "\n")
        log.event.error(message + advice)
        sys.exit(1)

    except Exception, e:
        message = "Error starting service: %s" % e
        sys.stderr.write("\n" + message + "\n")
        log.event.exception(message)
        sys.exit(1)
