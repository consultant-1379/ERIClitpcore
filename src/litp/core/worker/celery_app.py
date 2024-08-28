import os
import logging.config
from contextlib import contextmanager

import cherrypy
from celery import Celery
from celery.bin import Option
from celery import Task as CeleryTask
from celery.signals import setup_logging, user_preload_options
from celery.schedules import crontab

from litp.data.db_storage import DbStorage
from litp.data.db_storage import get_engine
from litp.data.data_manager import DataManager
from litp.core.litp_logging import LitpLogger
from litp.core.scope_utils import threadlocal_scope_context
from litp.core.nextgen.model_manager import ModelManager
from litp.core.nextgen.puppet_manager import PuppetManager
from litp.core.nextgen.execution_manager import ExecutionManager
from litp.core.nextgen.plugin_manager import PluginManager

import litp.metrics

log = LitpLogger()

celery_app = Celery('litp')

celery_app.user_options['preload'].add(
        Option('--litp-config-file', default='/etc/litpd.conf',
           help='Specify litpd config file, default /etc/litpd.conf'))

celery_app.user_options['preload'].add(
        Option('--litp-logging-conf', default='/etc/litp_logging.conf',
           help='logging conf, default /etc/litp_logging.conf'))

CELERY_DEFAULTS = {
    'BROKER_URL': 'amqp://',
    'CELERY_IMPORTS': ['litp.core.worker.tasks'],
    'CELERY_RESULT_DB_SHORT_LIVED_SESSIONS': True,
    'CELERYD_MAX_TASKS_PER_CHILD': 1,
    'CELERY_TRACK_STARTED': True,
    'CELERY_DISABLE_RATE_LIMITS': True,
    'CELERY_TASK_SERIALIZER': 'json',
    'CELERY_RESULT_SERIALIZER': 'json',
    'CELERY_ACCEPT_CONTENT': ['json'],
    'CELERY_DEFAULT_QUEUE': 'litp_default',
    'CELERY_DEFAULT_EXCHANGE': 'litp_default',
    'CELERY_DEFAULT_ROUTING_KEY': 'litp_default',
    'CELERY_ROUTES': {
        'litp.core.worker.tasks.run_plan_phase': {'queue': 'litp_task'},
        'litp.core.worker.tasks.run_plan': {'queue': 'litp_plan'},
        'litp.core.worker.tasks.monitor_plan': {'queue': 'litp_default'},
    },
    'CELERYBEAT_SCHEDULE': {
        'monitor_plan': {
            'task': 'litp.core.worker.tasks.monitor_plan',
            'schedule': crontab(minute="*"),
        },
    }
}


# suppress celery's internal logging config
@setup_logging.connect
def setup_logging(*args, **kwargs):
    # NOTE: connecting to this event is required
    # otherwise logged messages will be repeated on stdout
    pass


@user_preload_options.connect
def on_preload_parsed(options, **kwargs):
    cherrypy.config.update(options['litp_config_file'])
    # suppress cherrypy's internal logging config for non-service use.
    cherrypy.config.update({'log.screen': False,
                            'log.access_file': '',
                            'log.error_file': ''})
    cherrypy.engine.unsubscribe('graceful', cherrypy.log.reopen_files)
    logging.config.fileConfig(options['litp_logging_conf'])
    conf = {}
    conf.update(CELERY_DEFAULTS)
    if 'celery' in cherrypy.config:
        if 'CELERY_RESULT_BACKEND' in cherrypy.config.get('celery'):
            cherrypy.config['celery']['CELERY_RESULT_BACKEND'] = \
                cherrypy.config['celery']['CELERY_RESULT_BACKEND']\
                    .replace('\'', '')
        conf.update(cherrypy.config['celery'])
    celery_app.config_from_object(conf, force=True)
    celery_app.autodiscover_tasks(('litp.core.worker',), force=True)


def init_metrics():
    litp.metrics.set_handlers()


def is_db_schema_initialized():
    db_storage = DbStorage(get_engine(cherrypy.config))
    try:
        session = db_storage.create_session()
        data_manager = DataManager(session)
        try:
            # Don't really want to get a specific plan.
            # If no exception is raised on that query, the db is initialized.
            data_manager.get_plan('dummy_plan_id')
            return True
        except Exception:  # pylint:disable=broad-except
            return False
        finally:
            data_manager.close()
    finally:
        db_storage.close()


def configure_worker(engine, create_plugin_mgr=True, create_puppet_mgr=True):
    litp_root = cherrypy.config.get("litp_root", "/opt/ericsson/nms/litp")

    init_metrics()

    model_manager = ModelManager()

    plugin_manager = PluginManager(model_manager, daemon=False)
    if create_plugin_mgr:
        plugin_manager.add_extensions(os.path.join(
            litp_root, 'etc/extensions/'))
        plugin_manager.add_plugins(os.path.join(
            litp_root, 'etc/plugins/'))
    else:
        item_types_by_id = {}
        property_types_by_id = {}
        from litp.extensions.core_extension import CoreExtension
        core_extension = CoreExtension()
        core_item_types = core_extension.define_item_types()
        plugin_manager.ensure_unique_item_types(
            'core_extension', item_types_by_id, core_item_types
        )
        core_prop_types = core_extension.define_property_types()
        plugin_manager.ensure_unique_properties(
            'core_extension', property_types_by_id, core_prop_types
        )

        item_types = plugin_manager.get_sorted_item_types(item_types_by_id)
        plugin_manager.add_property_types(
            ept[0] for ept in property_types_by_id.values())
        plugin_manager.add_item_types(item_types)

    db_storage = DbStorage(engine)

    data_manager = DataManager(db_storage.create_session())
    data_manager.configure(model_manager)

    puppet_manager = None
    if create_puppet_mgr:
        puppet_manager = PuppetManager(model_manager, litp_root)

    execution_manager = ExecutionManager(
        model_manager, puppet_manager, plugin_manager)

    cherrypy.config.update({
        'db_storage': db_storage,
        'model_manager': model_manager,
        'puppet_manager': puppet_manager,
        'execution_manager': execution_manager,
        'plugin_manager': plugin_manager,
    })

    logging_item = data_manager.model.get("/litp/logging")
    data_manager.commit()
    data_manager.close()
    force_debug = False
    if logging_item:
        force_debug = (logging_item.force_debug == "true")
    model_manager.force_debug(
        force_debug=force_debug, normal_start=False)


def deconfigure_worker():
    db_storage = cherrypy.config["db_storage"]
    db_storage.close()


@contextmanager
def engine_context():
    engine = get_engine(cherrypy.config)
    yield engine


@contextmanager
def worker_context(engine):
    configure_worker(engine, create_plugin_mgr=True, create_puppet_mgr=True)
    try:
        yield
    finally:
        deconfigure_worker()


@contextmanager
def lean_worker_context(engine):
    configure_worker(engine, create_plugin_mgr=False, create_puppet_mgr=False)
    try:
        yield
    finally:
        deconfigure_worker()


class _BaseLitpTask(CeleryTask):
    # the app.task decorator dynamically builds a run method, suppress warning
    # pylint: disable=abstract-method
    abstract = True

    def __call__(self, *args, **kwargs):
        try:
            with engine_context() as engine:
                log.set_log_name(
                    "Celery({0})".format(self.__class__.__name__)
                )
                with self._get_worker_context()(engine):
                    with threadlocal_scope_context():
                        return CeleryTask.__call__(self, *args, **kwargs)

        except AttributeError as exception:
            # is_db_schema_initialized may cause a small race condition here
            # because the DB may get initialized after the AttributeError has
            # been raised and before the call, or during, the call of
            # is_db_schema_initialized. In this case an error would be
            # returned. Not a big deal for the monitor_plan task though.
            if self.name == 'litp.core.worker.tasks.monitor_plan' and \
                    not is_db_schema_initialized():
                return
            log.trace.error(exception, exc_info=True)
            return {'error': str(exception)}

        except Exception as exception:  # pylint: disable=W0703
            log.trace.error(exception, exc_info=True)
            return {'error': str(exception)}

    @classmethod
    def _get_worker_context(clazz):
        task_worker_context = getattr(clazz, 'task_setup_ctx_mgr')
        return task_worker_context.__func__


class FatTask(_BaseLitpTask):
    # pylint: disable=abstract-method
    abstract = True
    task_setup_ctx_mgr = worker_context

    def __call__(self, *args, **kwargs):
        return super(FatTask, self).__call__(*args, **kwargs)


class LeanTask(_BaseLitpTask):
    # pylint: disable=abstract-method
    abstract = True
    task_setup_ctx_mgr = lean_worker_context

    def __call__(self, *args, **kwargs):
        if not is_db_schema_initialized():
            return
        return super(LeanTask, self).__call__(*args, **kwargs)
