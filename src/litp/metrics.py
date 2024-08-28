import time
import logging
import logging.handlers
import contextlib
from grp import getgrnam
from pwd import getpwnam
from litp.core.litp_logging import LitpLogger
from litp.core.litp_logging import OwnedWatchedFileHandler
from litp.core.constants import CELERY_USER, CELERY_GROUP

LOG_FILENAME = '/var/log/litp/metrics.log'

logger = logging.getLogger('metrics')
logger.propagate = False
logger.setLevel(logging.INFO)

log = LitpLogger()


@contextlib.contextmanager
def time_taken_metrics(apply_metrics_logger):
    try:
        st = time.time()
        yield
    finally:
        et = time.time()
        apply_metrics_logger.log({'TimeTaken': '{0:.3f}'.format(et - st)})


def set_handlers(path=LOG_FILENAME):
    if logger.handlers:
        return
    try:
        handler = OwnedWatchedFileHandler(path,
                                          getpwnam(CELERY_USER).pw_uid,
                                          getgrnam(CELERY_GROUP).gr_gid)
    except KeyError as e:
        log.trace.warning("Could not get group id for group {0} "
                          "or user id for user {1}. {2}".
                          format(CELERY_GROUP, CELERY_USER, str(e)))
        raise e

    formatter = logging.Formatter(
        "%(asctime)s.%(msecs)d,%(message)s",
        datefmt="%Y-%m-%d %H:%M:%S")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.disabled = False


class MetricsLogger(object):
    def __init__(self, name):
        self.name = name
        self.parent = None
        self.id_handler = lambda: ''
        self.template = '{0}.{1}={2}'
        self.name_template = '[{0}]'

    @property
    def id(self):
        return self.id_handler()

    def extend_with(self, logger_name):
        new_logger = MetricsLogger(logger_name)
        new_logger.parent = self
        return new_logger

    def metric_prefix(self):
        names = [self.name + self.id]
        elem = self
        while elem.parent:
            names.insert(0, elem.parent.name + elem.parent.id)
            elem = elem.parent
        prefix = ''.join([self.name_template.format(n) for n in names])
        return prefix

    def log(self, metrics):
        # Re-enable logger in case litp disabled it calling logging.fileConfig
        logger.disabled = False
        for metric_name, metric_value in sorted(metrics.iteritems()):
            logger.info(
                self.template.format(self.metric_prefix(),
                                     metric_name,
                                     metric_value)
            )


def metrics_patch(
        obj, func_name, metric_logger, return_value_hook=None, args_hook=None,
        time_taken=True, **metrics):
    if return_value_hook is None:
        return_value_hook = lambda return_value: {}
    if args_hook is None:
        args_hook = lambda *args, **kwargs: {}

    def decorator_with_args(**metrics):
        def decorator(func):
            def metric_wrapped(*args, **kwargs):
                metrics_to_log = {}
                metrics_to_log.update(metrics)

                st = time.time()
                ret = func(*args, **kwargs)
                et = time.time()
                tt_metric = {'TimeTaken': '{0:.3f}'.format(et - st)}
                metrics_to_log.update(return_value_hook(ret))
                metrics_to_log.update(args_hook(*args, **kwargs))

                evaluated_metrics = {}
                for name, value in metrics_to_log.iteritems():
                    try:
                        if callable(value):
                            evaluated_metrics[name] = value()
                        else:
                            evaluated_metrics[name] = value
                    except Exception as e:  # pylint: disable=W0703
                        evaluated_metrics[name] = '<UnableToGetMetricsValue>'

                metric_logger.log(evaluated_metrics)
                if time_taken:
                    metric_logger.log(tt_metric)

                return ret
            return metric_wrapped
        return decorator

    function = getattr(obj, func_name)
    setattr(obj, func_name, decorator_with_args(**metrics)(function))


# This one is to be imported in modules
metrics_logger = MetricsLogger(name='LITP')
