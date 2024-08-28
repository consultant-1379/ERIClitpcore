##############################################################################
# COPYRIGHT Ericsson AB 2013
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################

import functools
import itertools
import inspect
import time
from collections import defaultdict, namedtuple
import re

import litp.core.constants as constants
from litp.core import scope
from litp.core.policies import LockPolicy
from litp.core.base_manager import BaseManager
from litp.core.exceptions import CorruptedConfFileException
from litp.core.exceptions import CyclicGraphException
from litp.core.plugin_context_api import PluginApiContext
from litp.core.litp_logging import LitpLogger
from litp.core.plan import Plan, SnapshotPlan
from litp.core.callback_api import CallbackApi
from litp.core.mixins import SnapshotExecutionMixin
from litp.core.plugin import Plugin
from litp.core.lock_task_creator import LockTaskCreator
from litp.service.utils import human_readable_timestamp
from litp.core.model_item import ModelItem
from litp.core.task import Task
from litp.core.task import ConfigTask
from litp.core.task import CallbackTask
from litp.core.task import CleanupTask
from litp.core.task import RemoteExecutionTask
from litp.core.task import OrderedTaskList
from litp.core.task import can_have_dependency_for_validation
from litp.core.model_manager import QueryItem
from litp.core.etlogger import ETLogger, et_logged
from litp.core.future_property_value import FuturePropertyValue
from litp.core.plan_builder import PlanBuilder, SnapshotPlanBuilder
from litp.core.plan_builder import _net_task_item_types
from litp.core.plan_builder import TaskCollection
from litp.core.plan_builder import GROUP_PRIORITY_INDEX
from litp.core.litp_threadpool import current_jobs
from litp.core.config import config
from litp.core.dotgraph import generate_dot_diagram
from litp.core.exceptions import EmptyPlanException, NoCredentialsException
from litp.core.exceptions import NodeLockException, NonUniqueTaskException
from litp.core.exceptions import PlanStateError, ServiceKilledException
from litp.core.exceptions import SnapshotError, TaskValidationException
from litp.core.exceptions import CallbackExecutionException
from litp.core.exceptions import PlanStoppedException, PluginError
from litp.core.exceptions import RemoteExecutionException, ViewError
from litp.core.exceptions import DataIntegrityException
from litp.core.rpc_commands import has_errors, run_rpc_command
from litp.plan_types.deployment_plan import DEPLOYMENT_PLAN_RULESET
from litp.plan_types.deployment_plan import deployment_plan_groups
from litp.plan_types.deployment_plan import deployment_plan_tags
from litp.plan_types.deployment_plan import DEPLOYMENT_PLAN_TAGS
from litp.data.constants import LAST_SUCCESSFUL_PLAN_MODEL_ID
from litp.data.constants import CURRENT_PLAN_ID
from litp.data.constants import SNAPSHOT_PLAN_MODEL_ID_PREFIX
from litp.enable_metrics import apply_metrics
# Celery does some magic with dynamic imports, hence pylint exceptions needed
# pylint:disable=import-error,no-name-in-module
from celery.task.control import inspect as celery_inspect
from celery.result import AsyncResult


log = LitpLogger()
etlog = ETLogger(log.trace.debug, "ExecutionManager ET")
et_logged = et_logged(etlog)

available_task_states = [
    constants.TASK_FAILED,
    constants.TASK_RUNNING,
    constants.TASK_STOPPED,
    constants.TASK_SUCCESS,
    constants.TASK_INITIAL,
]

base_snapshot_type = 'snapshot-base'


def create_item_task_dict(tasks):
    # {model_item: [tasks related to it]}
    result = defaultdict(list)
    for task in tasks:
        # When starting up after being shut down during the execution of a
        # resumed plan in which at least one task has a model item that was
        # removed from the model during a previous execution, it is
        # possible for litp to encounter model_item attributes that are
        # string vpaths
        if isinstance(task.model_item, basestring):
            result[task.model_item].append(task)
        else:
            result[task.model_item.vpath].append(task)
    return result


def create_all_items_task_dict(tasks):
    result = defaultdict(set)
    for task in tasks:
        for item in task.all_model_items:
            # When starting up after being shut down during the execution of a
            # resumed plan in which at least one task has a model item that was
            # removed from the model during a previous execution, it is
            # possible for litp to encounter model_item attributes that are
            # string vpaths
            if isinstance(item, basestring):
                result[item].add(task)
            else:
                result[item.vpath].add(task)
    return result


def create_task_dict_by_node_ct_ci(tasks):
    result = defaultdict(list)
    for task in tasks:
        result[(task.node.vpath, task.call_type, task.call_id)].append(task)
    return result


def log_defaultdict_list(d):
    for key, l in d.iteritems():
        log.trace.debug("  %s:", key)
        for item in l:
            log.trace.debug("    %s", item)


def is_cleanup_task(task):
    return isinstance(task, CleanupTask)


def is_deconfigure_task(task):
    return isinstance(task, ConfigTask)


def clear_celery_task(func):
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        try:
            ret = func(self, *args, **kwargs)
            return ret
        finally:
            # If we got so far it means the plan is over one way or another
            del self.plan.celery_task_id
            self.data_manager.commit()
    return wrapper


class ExecutionManagerNextGen(BaseManager, SnapshotExecutionMixin):
    def __init__(self, model_manager, puppet_manager, plugin_manager):
        super(ExecutionManagerNextGen, self).__init__()
        self.validation = {}
        self.model_manager = model_manager
        self.puppet_manager = puppet_manager
        self.plugin_manager = plugin_manager
        self.creating_plan = False
        self._outage_status = constants.NO_OUTAGE
        # This is populated in the snapshot controller
        self.exclude_nodes = set()
        self._active_phases = {}
        # subscribe to all puppet reports
        if puppet_manager is not None:
            self.puppet_manager.attach_handler('puppet_feedback',
                                               self.on_puppet_feedback)
            self.puppet_manager.attach_handler('puppet_timeout',
                                               self.on_puppet_timeout)
            self.puppet_manager.attach_handler('puppet_phase_start',
                                               self.on_puppet_phase_start)
            self.puppet_manager.attach_handler('on_mco_error',
                                               self.on_mco_error)
        apply_metrics(self)

    @property
    def plan(self):
        if not hasattr(scope, "plan"):
            scope.plan = self.data_manager.get_plan(CURRENT_PLAN_ID)

        if scope.plan is not None and scope.plan.is_active():
            if self._outage_status == constants.OUTAGE_DETECTED:
                # XXX This logic is known to be incorrect for TORF-124437 and
                # will have to be reworked
                dead_jobs = any(
                    self._is_job_dead(job) for job in current_jobs()
                )
                if dead_jobs:
                    log.trace.info("Invalidating unexpectedly halted plan")
                    self._fix_plan(scope.plan)
                    self._outage_status = constants.OUTAGE_HANDLED
        return scope.plan

    @staticmethod
    def _is_job_dead(job):
        if not job.processing:
            if isinstance(job.result, dict):
                if 'error' in job.result:
                    return True
        return False

    def outage_handler(self):
        if not (hasattr(scope, 'plan') and scope.plan is not None):
            return

        if self._outage_status == constants.NO_OUTAGE:
            if scope.plan.is_active():
                self._outage_status = constants.OUTAGE_DETECTED

    @plan.setter
    def plan(self, new_plan):
        old_plan = self.data_manager.get_plan(CURRENT_PLAN_ID)
        if old_plan:
            for plan_task in old_plan._plan_tasks:
                task = self.data_manager.get_task(plan_task.task_id)
                if isinstance(task, ConfigTask) and task._persisted_task:
                    continue
                self.data_manager.delete_task(task)
            self.data_manager.delete_plan(old_plan)
            self.data_manager.session.flush()

        if new_plan:
            new_plan._id = CURRENT_PLAN_ID
            new_plan.populate_plan_tasks()
            self.data_manager.add_plan(new_plan)

        scope.plan = new_plan

    @property
    def plan_type(self):
        return self.plan.plan_type

    def forget_cached_plan(self):
        if hasattr(scope, "plan"):
            if scope.plan in self.data_manager.session:
                self.data_manager.session.expire(scope.plan)
            del scope.plan

    def fix_plan_at_service_startup(self):
        self._fix_plan_at_service_startup()
        del scope.plan

    def _fix_plan_at_service_startup(self):
        plan = self.plan

        if not plan:
            return
        self._fix_plan(self.plan)

    def _fail_running_tasks(self, plan):
        for task in plan.get_tasks():
            if task.state == constants.TASK_RUNNING:
                task.state = constants.TASK_FAILED

    def _fix_plan(self, plan):
        if plan.is_initial():
            installed_plugins = set([
                (plugin["name"], plugin["class"], plugin["version"])
                for plugin in self.plugin_manager.get_plugin_info()])
            saved_plugins = set([
                (plugin_info.name, plugin_info.classpath, plugin_info.version)
                for plugin_info in self.data_manager.get_plugins()])
            installed_extensions = set([
                (ext["name"], ext["class"], ext["version"])
                for ext in self.plugin_manager.get_extension_info()])
            saved_extensions = set([
                (ext_info.name, ext_info.classpath, ext_info.version)
                for ext_info in self.data_manager.get_extensions()])
            if (
                installed_plugins != saved_plugins or
                installed_extensions != saved_extensions
            ):
                plan.mark_invalid()
            else:
                for task in plan.get_tasks():
                    if (
                        isinstance(task, RemoteExecutionTask) or
                        not isinstance(task, CallbackTask)
                    ):
                        continue
                    plugin = self.plugin_manager.get_plugin(task._plugin_class)
                    if not plugin:
                        raise DataIntegrityException(
                            "plan contains CallbackTask"
                            " with unknown plugin class:"
                            " \"{plugin_class}\"".format(
                                plugin_class=task._plugin_class))
                    if not hasattr(plugin, task._callback_name):
                        plan.mark_invalid()

        elif plan.is_active():
            if plan.celery_task_id:
                if self.celery_task_is_valid(plan):
                    return
                del plan.celery_task_id
            self._fail_running_tasks(plan)

            if not isinstance(plan, SnapshotPlan):
                self._set_applied_properties_determinable(plan)

            plan.end()

    def celery_task_is_valid(self, plan):
        '''
        It is to discover if celery is still running a plan after litp itself
        got restarted. If so, we don't want to fail the plan but we let it to
        continue.

        '''
        active_tasks = celery_inspect().active()
        celery_task_result = AsyncResult(plan.celery_task_id)

        ms_hostname = self.model_manager.get_item('/ms').hostname
        litp_plan_key = 'litpPlan@' + ms_hostname

        if not (active_tasks and
                litp_plan_key in active_tasks and
                active_tasks[litp_plan_key] and
                active_tasks[litp_plan_key][0]['id'] == plan.celery_task_id):
            return False
        elif celery_task_result.id != plan.celery_task_id or \
                celery_task_result.ready():
            return False

        return True

    def _commit(self):
        self.data_manager.commit()

    def sync(self):
        self._commit()
        self.data_manager.model.invalidate_cache()
        if hasattr(scope, "plan"):
            del scope.plan

    # PuppetManager event handlers
    def on_puppet_feedback(self, tasks_states):
        for task, state in tasks_states:
            if state not in available_task_states:
                raise RuntimeError(
                    "{0}'s state was requested to be changed to invalid: "
                    "{1}".format(task, state))
        self._puppet_report(tasks_states)
        self._commit()

    def on_puppet_timeout(self, tasks):
        timeout_nodes = set()
        for task in tasks:
            if task.state == constants.TASK_RUNNING:
                task.state = constants.TASK_FAILED
                timeout_nodes.add(task.node.hostname)
        if timeout_nodes:
            log_message = 'Failing running tasks due to Puppet timeout ' +\
                   'on node(s) ' +\
                   re.sub('(.*),', r'\1 and', ', '.join(sorted(timeout_nodes)))
            log.trace.info(log_message)
        self._commit()

    def on_puppet_phase_start(self, tasks, phase_id):
        for task in tasks:
            if task.state != constants.TASK_FAILED:
                task.state = constants.TASK_RUNNING
        self.sync()
        if self.plan.is_stopping():
            self._stop_running_phase_tasks(self.plan.phases[phase_id])
        self._commit()

    def on_mco_error(self, tasks):
        failed_nodes = set()
        for task in tasks:
            if task.state == constants.TASK_RUNNING:
                task.state = constants.TASK_FAILED
                failed_nodes.add(task.node.hostname)
        if failed_nodes:
            msg = 'Setting "Running" tasks to "Failed" on node(s) ' + \
                   re.sub('(.*),', r'\1 and', ', '.join(sorted(failed_nodes)))
            log.trace.info(msg)
        self._commit()

    def create_plan(self, plan_type=constants.DEPLOYMENT_PLAN,
                    lock_policies=None, node_path=''):
        return self._create_plan_with_type(plan_type,
            lock_policies=lock_policies,
            node_path=node_path)

    def create_snapshot_plan(self):
        plan_type = constants.CREATE_SNAPSHOT_PLAN
        return self._create_plan_with_type(plan_type)

    def delete_snapshot_plan(self):
        plan_type = constants.REMOVE_SNAPSHOT_PLAN
        return self._create_plan_with_type(plan_type)

    def restore_snapshot_plan(self):
        plan_type = constants.RESTORE_SNAPSHOT_PLAN
        return self._create_plan_with_type(plan_type)

    def _has_errors_before_create_plan(self, plan_type):
        self._update_model()
        self._validate_model(plan_type)
        if not self._is_model_valid():
            return self._validation_errors()
        try:
            self._get_security_credentials()
        except (NoCredentialsException, CorruptedConfFileException) as e:
            self.plan = None
            return self._format_exceptions(e, constants.CREDENTIALS_NOT_FOUND)

    def _create_plan_with_type(self, plan_type, lock_policies=None,
        node_path=''):
        """
        Creates or updates the Plan object bound to `self.plan` according to
        the current state of the model.
        :return A Plan object if plan creation has been successful, else a
        list of errors
        :type litp.core.plan.Plan or list
        """
        if lock_policies == None:
            lock_policies = []

        try:
            if plan_type == constants.REBOOT_PLAN:
                errors = self._get_core_plugin().\
                    validate_reboot_plan(self.model_manager, node_path)
                if errors:
                    errors = [err.to_dict() for err in errors]
            else:
                errors = self._has_errors_before_create_plan(plan_type)
        except PluginError as explicit_exception:
            return self._format_exceptions(
                explicit_exception,
                constants.INTERNAL_SERVER_ERROR
            )
        except Exception as validation_exception:
            return self._format_exceptions(
                validation_exception,
                constants.INTERNAL_SERVER_ERROR
            )

        if errors:
            return errors

        if plan_type in constants.SNAPSHOT_PLANS:
            # creating snapshot plan requires existing plan to be removed
            # creating standard plan might require tasks from existing plan
            self.plan = None
        for lock_policy in lock_policies:
            log.trace.info("Creating Plan with lock policy: %s.",
                           lock_policy.getAction())
            if lock_policy.getClusters():
                log.trace.info("Clusters: %s,", lock_policy.getClusters())

        plan = None
        self.creating_plan = True
        try:
            with self.model_manager.cached_model():
                plan = self._create_plan(
                    plan_type, lock_policies=lock_policies,
                    node_path=node_path)
                plan.set_ready()
        except EmptyPlanException:
            return self._format_exceptions(
                EmptyPlanException(self._get_empty_plan_err(plan_type)),
                constants.DO_NOTHING_PLAN_ERROR)
        except PluginError as e:
            return self._format_exceptions(e, constants.INTERNAL_SERVER_ERROR)
        except ViewError as e:
            return self._format_exceptions(e, constants.INTERNAL_SERVER_ERROR)
        except NodeLockException as e:
            return self._format_exceptions(e, constants.INTERNAL_SERVER_ERROR)
        except SnapshotError as e:
            return self._format_exceptions(e, constants.DO_NOTHING_PLAN_ERROR)
        except TaskValidationException as e:
            if e.messages:
                for message in e.messages:
                    log.trace.error(message)
            log.trace.error(e)
            return self._format_exceptions(e, constants.INTERNAL_SERVER_ERROR)
        except CyclicGraphException as e:
            log.trace.error(
                "Error while creating {0}, "
                "cyclic dependency found".format(
                    self._get_plan_log_msg(plan_type).lower())
            )
            name = generate_dot_diagram(e.graph)
            if name:
                log.trace.error("Graph dot file generated"
                               " {0}".format(name))
            else:
                log.trace.error("No graph dot file generated, "
                               "check parameter "
                               "\"task_graph_save_location\" in "
                               "litpd.conf")
            return self._format_exceptions(Exception('See logs for details.'),
                                           constants.INTERNAL_SERVER_ERROR)

        except Exception as e:
            log.trace.error('Error while creating %s',
                            self._get_plan_log_msg(plan_type).lower())
            log.trace.error(e, exc_info=True)
            return self._format_exceptions(Exception('See logs for details.'),
                                           constants.INTERNAL_SERVER_ERROR)
        finally:
            self.plan = plan
            self.creating_plan = False
            self._outage_status = constants.NO_OUTAGE

        if plan:
            log.event.info("%s created", self._get_plan_log_msg(plan_type))
        else:
            log.event.info("Failure to create %s",
                           self._get_plan_log_msg(plan_type).lower())

        return plan

    def _get_plan_log_msg(self, plan_type):
        msg = '%s Plan' % plan_type
        return msg.title()

    def _format_exceptions(self, e, error_type):
        # allows plugins to return several errors in create_plan
        def create_err(err, error_type):
            return {"error": error_type, "message": str(err)}
        errs = []
        if e.args and isinstance(e.args[0], (list, set)):
            errs = [create_err(err, error_type) for err in e.args[0]]
        else:
            errs.append(create_err(e, error_type))
        return errs

    def _get_empty_plan_err(self, plan_type, name=''):
        basemsg = "no tasks were generated"
        if not name:
            name = PluginApiContext(self.model_manager).snapshot_name()
        snapshot_item = self.model_manager.query(
            base_snapshot_type,
            item_id=name
        )
        snapshot_status = self.snapshot_status(name)
        if 'snapshot' not in plan_type:
            return basemsg
        if 'exists' in snapshot_status:
            return basemsg + ". No snapshot tasks added because "\
                    "Deployment Snapshot with timestamp {0} exists".format(\
                    human_readable_timestamp(snapshot_item[0]))
        elif snapshot_status == 'failed':
            return basemsg + ". No snapshot tasks added because "\
                             "failed Deployment Snapshot exists"

        if constants.REMOVE_SNAPSHOT_PLAN == plan_type and \
        snapshot_status == 'no_snapshot':
            if name == 'snapshot':
                return basemsg + ". No remove snapshot tasks added because "\
                        "Deployment Snapshot does not exist."
            else:
                return basemsg + ". No remove snapshot tasks added because "\
                        "Named Backup Snapshot \"%s\" does not exist." % name

        if constants.RESTORE_SNAPSHOT_PLAN == plan_type and \
           snapshot_status == 'not_started_yet':
            return basemsg + ".  No Deployment Snapshot to be restored"

        if snapshot_item:
            if not snapshot_item[0].is_applied():
                return basemsg + ". No snapshot tasks added because "\
                                 "failed Deployment Snapshot exists"
        return basemsg

    def _plan_related_to_snapshot(self, snapshot_name):
        # returns True if the snapshot_name belongs to the active snapshot for
        # that plan
        return self.plan_has_tasks() and \
          PluginApiContext(self.model_manager).snapshot_name() == snapshot_name

    def plan_exists(self):
        return bool(self.plan)

    def plan_has_tasks(self):
        plan = self.plan
        return bool(plan)

    def plan_state(self):
        plan = self.plan
        return plan.state if plan else None

    def delete_plan(self, by_user=True):
        plan = self.plan
        if plan is None:
            return {'error': 'Plan does not exist'}
        plan_type = plan.plan_type
        self.plan = None
        # Log event, but not if this is an internal operation
        # (e.g. cleaning up after a failed restore_snapshot).
        if by_user:
            log.event.info('%s Plan removed by user' % plan_type)
        return {"success": "plan deleted"}

    def plan_phases(self):
        plan = self.plan
        return plan.phases if plan else []

    def stop_plan(self):
        plan = self.plan
        try:
            log.trace.debug("stop_plan()")
            if not plan:
                return {"error": "Plan does not exist"}
            plan.stop()
            self.puppet_manager.phase_stopped = True
            self._commit()
        except PlanStateError as e:
            return {'error': str(e)}

        return {"success": "Plan stopping"}

    def kill_plan(self):
        self.puppet_manager.killed = True
        if self.plan_exists():
            log.trace.debug("Killing plan")
            self.stop_plan()
            self._commit()
            while True:
                self.forget_cached_plan()
                if not self.is_plan_active():
                    break
                time.sleep(0.5)
            self.forget_cached_plan()
            if self.is_plan_stopped():
                for phase in self.plan.phases:
                    self._stop_running_phase_tasks(phase)
                self._commit()

    def is_running(self):
        self.data_manager.refresh(self.plan)
        return self.is_plan_running()

    def get_vpath(self):
        return '/execution'

    def _process_callback_task(self, task):

        log.trace.debug("Processing Callback Task: %s", task)
        try:
            task.state = constants.TASK_RUNNING
            self._commit()

            if isinstance(task, RemoteExecutionTask):
                callback = getattr(task, task._callback_name)
            else:
                plugin = self.plugin_manager.get_plugin(task._plugin_class)
                callback = getattr(plugin, task._callback_name)
            result = callback(
                CallbackApi(self), *task.args, **task.kwargs)
            log.trace.debug("Ran task:%s result:%s", task, result)
        except (CallbackExecutionException, RemoteExecutionException) as e:
            log.event.error(
                "%s running task: %s; (Exception message: '%s')",
                type(e).__name__, task.description, e)
            log.event.debug(
                "%s running task: %s; (Exception message: '%s')",
                type(e).__name__, task, e)
            task.state = constants.TASK_FAILED
            log.trace.debug(e, exc_info=True)
            return None, {'error': str(e)}

        except PlanStoppedException as e:
            log.event.info(
                "%s running task: %s; (Exception message: '%s')",
                type(e).__name__, task, e)
            task.state = constants.TASK_STOPPED
            log.trace.debug(e, exc_info=True)
            return None, {'error': str(e)}
        except Exception as e:
            log.trace.exception("Exception running task: %s", task)
            task.state = constants.TASK_FAILED
            return None, {'error': str(e)}
        task.state = constants.TASK_SUCCESS
        self._set_task_lock(task)

        return "success", None

    def _set_task_lock(self, task):
        if task.state == constants.TASK_SUCCESS \
                and task.lock_type == Task.TYPE_LOCK:
            task._locked_node.set_property("is_locked", "true")
        elif task.state == constants.TASK_SUCCESS \
                and task.lock_type == Task.TYPE_UNLOCK:
            task._locked_node.set_property("is_locked", "false")

    def _evaluate_future_property_values(self, tasks):
        for task in tasks:
            self._evaluate_task_future_property_values(task)

    def _evaluate_task_future_property_values(self, task):
        if (
            isinstance(task, (ConfigTask, CallbackTask)) and
            self._has_future_property_value(task.kwargs)
        ):
            kwargs = {}
            for key, val in task.kwargs.iteritems():
                try:
                    kwargs[key] = self._evaluate_params(val)
                except ViewError:
                    log.trace.error('Error while evaluating the argument '
                            '"%s" of FuturePropertyValue in task %s' %
                            (key, task))
                    task.state = constants.TASK_FAILED
                    break
            if task.state != constants.TASK_FAILED:
                task.kwargs = kwargs
        if (
            isinstance(task, CallbackTask) and
            self._has_future_property_value(task.args)
        ):
            args = []
            for val in task.args:
                try:
                    args.append(self._evaluate_params(val))
                except ViewError:
                    log.trace.error('Error while evaluating the argument '
                            '"%s" of FuturePropertyValue in task %s' %
                            (val, task))
                    task.state = constants.TASK_FAILED
                    break
            args = tuple(args)
            if task.state != constants.TASK_FAILED:
                task.args = args

    def _has_future_property_value(self, val):
        ret = False
        if isinstance(val, list):
            for v in val:
                ret = self._has_future_property_value(v)
                if ret:
                    break
        elif isinstance(val, dict):
            for v in val.itervalues():
                ret = self._has_future_property_value(v)
                if ret:
                    break
        elif isinstance(val, FuturePropertyValue):
            ret = True
        return ret

    def _evaluate_params(self, val):
        if isinstance(val, FuturePropertyValue):
            val = val.value
        elif isinstance(val, list):
            val = [self._evaluate_params(item) for item in val]
        elif isinstance(val, dict):
            val = dict([
                (k, self._evaluate_params(v)) for k, v in val.iteritems()])
        return val

    @clear_celery_task
    def run_plan(self, celery_request_id=None):
        """
        Executes the Plan object bound to `self.plan`.
        :param celery_request_id: The Task.request.id used for plan execution
        :type celery_request_id: str

        :return: A dictionary with either {'success': 'Plan Complete'} or
            {'error': [<list of errors>]}
        :rtype: dict
        """

        # Case when celery plan worker gets restarted while executing a plan
        if self.plan.is_active():
            self._fail_running_tasks(self.plan)
            if not isinstance(self.plan, SnapshotPlan):
                self._set_applied_properties_determinable(self.plan)
            self._run_plan_complete(False)
            return {'error': ['Plan worker died while executing a plan']}

        log.event.info('%s Plan execution begins', self.plan.plan_type)
        log.event.info(
            '%s Plan execution on celery task %s',
            self.plan.plan_type,
            celery_request_id)
        log.trace.debug('ExecutionManager.run_plan() called')
        if self.is_snapshot_plan:
            plugin_api_context = PluginApiContext(self.model_manager)
            snapshot_action = plugin_api_context.snapshot_action()
            snapshot_name = plugin_api_context.snapshot_name()
            if snapshot_action == 'create':
                self._backup_model_for_snapshot()
        else:
            self.invalidate_restore_model()
        self._commit()

        # TODO: is this populate_plan_tasks actually necessary?
        self.plan.populate_plan_tasks()
        self._disable_puppet(check_reachable=True)
        result = self._run_plan_start()
        if result:
            return result

        try:
            self.plan.celery_task_id = celery_request_id
            self.data_manager.commit()
            result = self._run_all_phases()
        except:
            self._run_plan_complete(False)
            raise

        if result:
            self._run_plan_complete(False)
            return result
        self._run_plan_complete(True)

        if self.is_snapshot_plan:
            if snapshot_action == 'remove':
                self.invalidate_snapshot_model(snapshot_name)
        else:
            self._backup_model_for_restore()
        self._commit()

        return self._run_plan_success()

    def invalidate_restore_model(self):
        model_id = LAST_SUCCESSFUL_PLAN_MODEL_ID
        self.data_manager.model.delete_backup(model_id)

    def invalidate_snapshot_model(self, snapshot_name):
        if not snapshot_name:
            log.trace.info('No snapshot available.')
            return

        model_id = SNAPSHOT_PLAN_MODEL_ID_PREFIX + snapshot_name
        self.data_manager.model.delete_backup(model_id)

    def _backup_model_for_restore(self):
        model_id = LAST_SUCCESSFUL_PLAN_MODEL_ID
        self.data_manager.model.create_backup(model_id)

    def _backup_model_for_snapshot(self):
        snapshot_name = PluginApiContext(
            self.model_manager).snapshot_name()
        if not snapshot_name:
            return

        model_id = SNAPSHOT_PLAN_MODEL_ID_PREFIX + snapshot_name
        self.data_manager.model.create_backup(model_id)

    ActivePhaseHolder = namedtuple('ActivePhaseHolder', (
        'phase_index',
        'async_result',
        'result'))

    def _enqueue_ready_phases(self, overall_result, last_phase_idx=-1):
        new_batch = self._run_next_phases(last_phase_idx)

        for aph in new_batch:
            if aph.async_result is not None:
                self._active_phases[aph.phase_index] = aph.async_result
            elif aph.result is not None:
                # The phase has been run synchronously as part of the call to
                # _run_next_phases()
                if not overall_result['errors']:
                    overall_result['error'] = aph.result['error']
                overall_result['errors'][aph.phase_index] = aph.result

    # TODO It is known that Celery provides lowlevel callback (link/link_error)
    # and highlevel "canvas" functionality, that would likely be a lot more
    # efficient to use than doing this...
    def _run_all_phases(self):
        overall_result = {
            'errors': {},
        }
        # Prepare a set of model items with plugin-updatable properties
        etlog.begin("Building set of runtime-updatable items")
        updatable_items = self.model_manager.get_plugin_updatable_items()
        etlog.done()

        self._active_phases.clear()

        self._enqueue_ready_phases(overall_result)

        i = 0
        while self._active_phases:
            for phase_index, async_result in self._active_phases.items():
                if not async_result.ready():
                    continue

                # This phase has finished running
                del self._active_phases[phase_index]

                for instance in self.data_manager.session.identity_map.\
                        itervalues():
                    if not isinstance(instance, ModelItem):
                        self.data_manager.session.expire(instance)
                    else:
                        if instance.vpath in updatable_items:
                            self.data_manager.session.expire(instance)
                self.forget_cached_plan()
                self._commit()

                if self.is_plan_active():
                    self._update_item_states(self.plan.phases[phase_index])
                    self._commit()

                if async_result.failed():
                    phase_result = {'error': str(async_result.result)}
                else:
                    phase_result = async_result.result

                # Truthy result is bad result
                # error is for backward-compat, first error found
                # errors is all errors found by phase
                if phase_result:
                    if not overall_result['errors']:
                        overall_result['error'] = phase_result['error']
                    overall_result['errors'][phase_index] = phase_result

                # TORF-124437: Only spawn new phases if nothing has failed.
                if not overall_result['errors']:
                    self._enqueue_ready_phases(overall_result, phase_index)

            time.sleep(0.25)
            if i % 100 == 0:
                log.trace.info(
                    "[%s]: Waiting on %s (%d iterations)" % (
                        self.__class__.__name__, self._active_phases, i
                    )
                )
            i = i + 1

        if not overall_result['errors']:
            del overall_result['errors']

        # If celery worker got killed it is possible there are tasks left in
        # constants.TASK_RUNNING state. Since the entire plan is failed in such
        # case, all of these have to be set to constants.TASK_FAILED.
        self._fail_running_tasks(self.plan)
        return overall_result

    def fix_removed_items_on_resume(self):
        items_to_fix = set()
        for task in self.plan.get_tasks():
            if task.state != constants.TASK_SUCCESS:
                continue
            for task_item in task.all_model_items:
                if task_item._model_item.previous_state == ModelItem.Removed:
                    items_to_fix.add(task_item._model_item)

        log.trace.debug(
            "Reversing transition away from Removed for: %r", items_to_fix
        )
        for item_to_fix in items_to_fix:
            item_to_fix.set_removed()

    def _run_next_phases(self, last_phase=-1):
        """
        Execute next phases given the last completed

        returns a list of ActivePhaseHolder namedtuples - one for each phase
        that has been enqueued
        """
        plan = self.plan
        results = []
        for phase_index in plan.ready_phases(last_phase):
            # run cleanup phases synchronously
            _, _, cleanup_tasks = self._analyse_phase(phase_index)
            if cleanup_tasks:
                result = self._run_plan_phase_in_worker(phase_index)
                results.append(
                    self.ActivePhaseHolder(phase_index, None, result))
            else:
                from litp.core.worker.tasks import run_plan_phase
                async_result = run_plan_phase.s(phase_index).apply_async()
                results.append(
                    self.ActivePhaseHolder(phase_index, async_result, None))
        return results

    def _run_plan_start(self):
        log.trace.debug("_run_plan_start")
        try:
            self.plan.run()
        except PlanStateError as e:
            return {'error': str(e)}
        finally:
            self._commit()

    def worker_run_plan_phase(self, phase_index):
        try:
            return self._run_plan_phase_in_worker(phase_index)
        finally:
            self.data_manager.commit()

    def _run_plan_phase(self, phase_index):
        # deprecated, only UTs and ATrunner call this method
        ret = self._run_plan_phase_in_worker(phase_index)
        if self.plan.is_active():
            self._update_item_states(self.plan.phases[phase_index])
        return ret

    def _run_plan_phase_in_worker(self, phase_index):
        log.event.info('Running phase %s', str(phase_index + 1))
        self.forget_cached_plan()
        plan = self.plan
        phase = plan.phases[phase_index]
        if plan.is_stopping():
            log.event.info('Plan stopped by user')
            self._stop_running_phase_tasks(phase)
            self._commit()
            return {'error': 'Plan Stopped'}

        try:
            self._set_phase_atts(phase_index)
            if phase_index == 0:
                self._process_timestamp_at_ss_phasestart(phase_index)
            result = self._run_phase(phase_index)
            if phase_index == (len(self.plan.phases) - 1):
                self._process_timestamp_at_ss_phaseend(phase_index, result)
            if result:
                log.event.info('Phase %s failed', str(phase_index + 1))
                return result
            log.event.info('Phase %s successful', str(phase_index + 1))
        finally:
            self._reset_phase_atts()

    def _run_plan_success(self):
        log.trace.debug("_run_plan_success")
        if self.is_plan_active():
            log.event.info('Plan completed successfully')

        self._enable_puppet(check_reachable=True)

        return {'success': 'Plan Complete'}

    def _run_plan_complete(self, successful):
        log.trace.debug("_run_plan_complete")
        # all phases should have completed and committed
        self.sync()
        # expire_on_commit=False on our session.
        self.data_manager.session.expire_all()
        plan = self.plan
        try:
            self._clear_plan(successful)
            # Litp cannot leave Puppet disabled. Always re-enable it.
            self._enable_puppet(check_reachable=True)
            self.forget_cached_plan()
            plan.end()
            log.trace.debug("plan state: " + plan.state)
            if successful:
                log.event.info(
                    '%s Plan execution successful' % plan.plan_type
                )
            elif not plan.is_stopped():
                log.event.error('%s Plan execution unsuccessful' %
                                plan.plan_type)
        finally:
            self._commit()

    def _get_all_hostnames(self, include_ms=True, check_reachable=False):
        hostnames = set()
        for node in self.model_manager.get_all_nodes():
            if not node.is_for_removal():
                if node.is_ms():
                    if include_ms:
                        hostnames.add(node.hostname)
                else:
                    hostnames.add(node.hostname)

        all_hostnames = hostnames & set(self.puppet_manager.node_tasks.keys())
        sorted_hostnames = sorted(list(all_hostnames))
        if check_reachable:
            return [hostname for hostname in sorted_hostnames
                        if self._is_node_reachable(hostname)]
        return sorted_hostnames

    def _enable_puppet(self, check_reachable=False):
        hostnames = self._get_all_hostnames(check_reachable=check_reachable)
        log.event.info(
            "Enabling Puppet on nodes: %s",
            re.sub('(.*),', r'\1 and', ', '.join(hostnames))
        )
        self.puppet_manager.mco_processor.enable_puppet(hostnames, timeout=30)

    def _disable_puppet(self, check_reachable=False):
        hostnames = self._get_all_hostnames(include_ms=False,
                                            check_reachable=check_reachable)
        log.event.info(
            "Disabling Puppet on nodes: %s",
            re.sub('(.*),', r'\1 and', ', '.join(hostnames))
        )
        self.puppet_manager.mco_processor.disable_puppet(hostnames)

    def _is_node_reachable(self, node):
        result = run_rpc_command([node], "rpcutil", "ping", timeout=4)
        if result:
            # log.event.info("Result of mco rpc command {0}".format(result))
            try:
                if not result[node]['errors']:
                    return True
            except KeyError as e:
                log.trace.warning("No {0} in command output. {1}".format(
                                                                node, str(e)))
                return False
        return False

    def _set_phase_atts(self, phase_id):
        self.plan.current_phase = phase_id
        self._commit()

    def _reset_phase_atts(self):
        self.plan.current_phase = None
        self._commit()

    @property
    def is_snapshot_plan(self):
        plan = self.plan
        return plan and isinstance(plan, SnapshotPlan)

    def is_plan_running(self):
        plan = self.plan
        return plan and plan.is_running()

    def is_plan_stopping(self):
        plan = self.plan
        return plan and plan.is_stopping()

    def is_plan_stopped(self):
        plan = self.plan
        return plan and plan.is_stopped()

    def is_plan_active(self):
        plan = self.plan
        return plan and plan.is_active()

    def model_changed(self):
        plan = self.plan
        if plan and (plan.is_initial() or plan.is_failed()):
            plan.mark_invalid()

    def can_create_plan(self):
        plan = self.plan
        if plan is None:
            return not self.creating_plan
        else:
            return plan.can_create_plan()

    def _set_applied_properties_determinable(self, plan=None):
        plan = plan or self.plan
        item_tasks = create_all_items_task_dict(plan.get_tasks())
        self.model_manager._set_applied_properties_determinable(item_tasks)

    def _clear_plan(self, successful):
        # Backup the manifest if the plan has failed

        # The nodes whose hostnames we add to that set will be the target of
        # the PuppetManager's apply_removal() method
        failed_manifest_nodes = set()
        if not successful:
            # Collect the hostnames of nodes with broken manifests
            for task in self.plan.get_tasks():
                if not isinstance(task, ConfigTask):
                    continue
                if task.node.is_for_removal():
                    continue
                if task.state == constants.TASK_FAILED:
                    failed_manifest_nodes.add(task.node.hostname)

        self.puppet_manager.cleanup(
            self.plan.get_tasks(CleanupTask),
            failed_manifest_nodes
        )

        self.model_manager.delete_removed_items_after_plan()

        if successful:
            if self.is_snapshot_plan:
                ss_obj = self.current_snapshot_object()
                if ss_obj:
                    self.model_manager.set_snapshot_applied(ss_obj.item_id)
            elif self.plan.plan_type != constants.REBOOT_PLAN:
                # we don't want the snapshot item to be applied in a
                # non-snapshot plan, see litpcds-8537
                exceptions = [base_snapshot_type]
                self.model_manager.set_all_applied(exceptions=exceptions)

        if not self.is_snapshot_plan and \
        self.plan.plan_type != constants.REBOOT_PLAN:
            self._set_applied_properties_determinable()

        self._reset_phase_atts()

    def _analyse_phase(self, phase_id):
        """
        Categorize a plan phase as Config, Callback or Cleanup

        :param int phase_id: The index of the phase in the plan
        :return: (config_tasks, callback_tasks, cleanup_tasks)
        :rtype: tuple
        :raises ValueError: if phase has mixed task types (shouldn't happen)
        """
        plan = self.plan
        phase = plan.get_phase(phase_id)
        log.trace.debug('Tasks in phase: %s', phase)

        config_tasks = []
        callback_tasks = []
        cleanup_tasks = []
        for task in phase:
            if isinstance(task, ConfigTask):
                config_tasks.append(task)
            elif isinstance(task, CallbackTask):
                callback_tasks.append(task)
            elif isinstance(task, CleanupTask):
                cleanup_tasks.append(task)

        if (
                bool(config_tasks), bool(callback_tasks), bool(cleanup_tasks)
                ).count(True) > 1:
            raise ValueError("mixed phases are not supported")

        return config_tasks, callback_tasks, cleanup_tasks

    def _run_phase(self, phase_id):
        config_tasks, callback_tasks, cleanup_tasks = self._analyse_phase(
            phase_id)
        if config_tasks:
            return self._run_puppet_phase(phase_id, config_tasks)
        elif callback_tasks:
            return self._run_callback_phase(phase_id, callback_tasks)
        elif cleanup_tasks:
            return self._run_cleanup_phase(phase_id, cleanup_tasks)

    def _run_cleanup_phase(self, phase_id, cleanup_tasks):
        """
        Run cleanup tasks in a phase
        """
        for task in cleanup_tasks:
            task.state = constants.TASK_SUCCESS
        self._update_item_states(cleanup_tasks)

    def _stop_running_phase_tasks(self, phase_tasks):
        """
        Changes the state of any running tasks in a phase to stopped.
        """
        log.trace.debug("Stopping running tasks")
        for task in phase_tasks:
            if task.state == constants.TASK_RUNNING:
                task.state = constants.TASK_STOPPED

    def _run_puppet_phase(self, phase_id, puppet_phase):
        self._evaluate_future_property_values(puppet_phase)
        self.data_manager.commit()
        if any(
                task.state == constants.TASK_FAILED
                for task in puppet_phase):
            return {'error': 'FuturePropertyValue evaluation error'}

        self.puppet_manager.add_phase(puppet_phase, phase_id)
        self.data_manager.commit()

        log.trace.info("Applying Puppet tasks")
        try:
            ret = self.puppet_manager.apply_nodes()
            if has_errors(ret):
                return {'error': ret}

            ret = self._wait_for_puppet_manager(puppet_phase)

            self.puppet_manager.restore_backed_up_tasks()
            self.data_manager.commit()

            return ret

        except ServiceKilledException as e:
            return {'error': str(e)}

    def _run_callback_phase(self, phase_id, callback_phase):
        """
        Executes the callback tasks in a given phase
        :param list callback_phase: The callback tasks in that phase
        """

        if callback_phase:
            log.trace.debug("Processing Callback tasks: %s", callback_phase)
            for task in callback_phase:
                log.trace.debug("processing callback task:%s", task)
                # This can happen in a plan resumption scenario
                if task.state == constants.TASK_SUCCESS:
                    continue
                try:
                    success, errors = self._process_callback_task(task)
                finally:
                    self._commit()
                log.trace.debug(
                    "callback task completed %s:%s", success, errors)
                if not success:
                    return {'error': errors}
            if self.is_plan_active():
                self._log_phase_completion()

    def _is_phase_complete(self, index):
        return all(task.has_run() for task in self.plan.get_phase(index))

    @et_logged
    def _update_item_states(self, tasks):
        """
        Updates states of the ModelItems associated with the given tasks based
        on the states of all the tasks in the plan.
        """

        log.trace.debug("_update_item_states")

        model_items = set()
        for task in tasks:
            if task.state == constants.TASK_FAILED:
                if not isinstance(task, CallbackTask):
                    log.event.debug('Task %s failed', task)
            elif task.state == constants.TASK_SUCCESS:
                log.trace.debug("Success: %s", task)
            model_items |= task.all_model_items

        mi_set = set()
        for model_item in model_items:
            if isinstance(model_item, basestring):
                continue
            mi_set.add(model_item._model_item)
        model_items = mi_set

        plan = self.plan
        for model_item in model_items:
            acting_tasks = plan.find_tasks(model_item=model_item)
            success_acting_tasks = set()
            failed_acting_tasks = set()
            for task in acting_tasks:
                if task.state == constants.TASK_SUCCESS:
                    success_acting_tasks.add(task)
                elif task.state == constants.TASK_FAILED:
                    # necessary? it's only used for logging
                    failed_acting_tasks.add(task)

            # log model items that won't be applied due to failed tasks
            # possibly unnecessary - do we need to log it?
            if failed_acting_tasks:
                log.trace.debug("%s won't change state due to failure of %s.",
                                model_item, failed_acting_tasks)
            elif acting_tasks == success_acting_tasks:
                if (self.is_snapshot_plan
                        and not model_item.is_instance(base_snapshot_type)):
                    continue
                # all relevant tasks completed successfully
                if model_item.is_for_removal():
                    model_item.set_removed()
                    log.trace.debug("Removed: %s", model_item)
                elif self.is_snapshot_plan:
                    # possibly unnecessary branch - do we need to log it?
                    log.trace.debug("%s can't be set to 'Applied' "
                                    "in snapshot phase.", model_item)
                elif model_item.is_initial() or model_item.is_updated():
                    model_item.set_applied()
                    log.trace.debug("Applied: %s", model_item)

    def _failed_tasks_in_phase(self, phase_id):
        return self.plan.find_tasks(phase=phase_id,
                                    state=constants.TASK_FAILED)

    def _puppet_report(self, tasks_states_pairs):
        log.trace.debug("ExecutionManager._puppet_report()")
        log.trace.debug("is_plan_active? %s", self.is_plan_active())
        plan = self.plan
        if self.is_plan_active():
            log.trace.debug("plan.current_phase: %s", plan.current_phase)

        if self.is_plan_active() and plan.current_phase is not None:
            tasks = []
            for task, state in tasks_states_pairs:
                task.state = state
                self._set_task_lock(task)
                tasks.append(task)

            self._log_phase_completion()
            return True
        return False

    def _log_phase_completion(self):
        plan = self.plan
        log.trace.debug("ExecutionManager._log_phase_completion()")
        log.trace.debug("plan?: %s", bool(plan))
        phase_id = plan.current_phase if plan else None
        log.trace.debug("phase_id: %s", phase_id)
        if phase_id is None:
            return
        all_phase_tasks = plan.find_tasks(phase='current')
        completed = [constants.TASK_FAILED, constants.TASK_SUCCESS]
        if all(t.state in completed for t in all_phase_tasks):
            log.event.info('Phase %s completed', phase_id + 1)
        else:
            log.trace.debug("Phase not completed")

    def _wait_for_puppet_manager(self, puppet_phase):
        # Need to check whether all tasks have already been transitioned to an
        # applied state by _process_feedback while the callback tasks were
        # runnning
        if len(puppet_phase) != 0 and \
                not all(task.has_run() for task in puppet_phase):
            log.trace.debug("Waiting for Puppet phase to complete")
            timeout = config.get('puppet_phase_timeout', 43200)
            poll_freq = config.get('puppet_poll_frequency', 60)
            poll_count = config.get('puppet_poll_count', 5)
            success = self.puppet_manager.wait_for_phase(puppet_phase,
                                                         timeout=timeout,
                                                         poll_freq=poll_freq,
                                                         poll_count=poll_count)
            basemsg = "Puppet phase completed"
            basemsg += " successfully" if success else " with errors"
            log.trace.debug(basemsg)
            if not success:
                return {'error': 'puppet errors'}

        failed_states = set([constants.TASK_FAILED, constants.TASK_STOPPED])
        if any(task.state in failed_states for task in puppet_phase):
            log.trace.debug("Puppet phase completed with errors")
            return {'error': 'puppet errors'}
        else:
            self.puppet_manager.disable_puppet_on_hosts(
                                            task_state=constants.TASK_SUCCESS)

    def _update_model(self):
        """
        Invokes the update_model() method on plugins to allow them to
        modify the model before it is validated and a plan is created.
        """

        for name, plugin in self.plugin_manager.iter_plugins():
            log.trace.debug("plugin %s update_model", name)
            try:
                plugin.update_model(PluginApiContext(self.model_manager))
            except PluginError as err:
                log.trace.error(
                    "Plugin Error in %s while updating model", name)
                raise PluginError("Model update failed with: %s" % (str(err)))
            except Exception as ex:
                log.trace.exception("Uncaught exception while updating model"
                    " from plugin: %s", name)
                raise Exception("Model update failed with: %s" % (str(ex)))

    def _validate_model(self, plan_type):
        """
        Performs model validation using the ModelManager class as well as the
        validators delivered by plugins.
        """
        _plan_type = plan_type.lower()
        is_snapshot_plan = _plan_type in constants.SNAPSHOT_PLANS

        errors = {}
        log.trace.debug("validate model")

        if not is_snapshot_plan:
            errors['ModelManager'] = self.model_manager.validate_model()

        for name, plugin in self.plugin_manager.iter_plugins():
            log.trace.debug("plugin %s validate_model", name)
            try:
                if is_snapshot_plan:
                    errors[name] = plugin.validate_model_snapshot(
                        PluginApiContext(self.model_manager)
                    )
                else:
                    errors[name] = plugin.validate_model(
                        PluginApiContext(self.model_manager))
            except Exception as ex:
                log.trace.exception("Uncaught exception while validating model"
                    " from plugin: %s", name)
                raise Exception("Model validation failed with: %s" % (str(ex)))

        self.validation = errors
        log.trace.debug("Validation errors found: %s", self.validation)

    def _is_model_valid(self):
        return self._validation_errors() == []

    def _validation_errors(self):
        errors = itertools.chain(*[error for error in
                                 self.validation.values()])
        return [err.to_dict() for err in errors]

    def _validate_tasks(self, _, tasks):
        for task in tasks:
            task.validate()

            if type(task) is CallbackTask:
                if (
                    not inspect.ismethod(task.callback) or
                    Plugin not in inspect.getmro(task.callback.im_class)
                ):
                    raise TaskValidationException(
                        "CallbackTask must use a method of the Plugin")

    def _get_task_node(self, task):
        if isinstance(task, ConfigTask):
            return task.node
        elif isinstance(task, RemoteExecutionTask):
            if len(task.nodes) != 1:
                raise ValueError("no or multiple nodes for task: %s" % task)
            return iter(task.nodes).next()
        elif isinstance(task, CallbackTask):
            return task.get_node_for_model_item()
        else:
            raise ValueError("unknown type for task: %s" % task)

    def _validate_task_group(self, tasks):
        for task in tasks:
            if isinstance(task, ConfigTask):
                continue
            groups = [deployment_plan_groups.NODE_GROUP,
                      deployment_plan_groups.CLUSTER_GROUP,
                      deployment_plan_groups.PRE_NODE_CLUSTER_GROUP]
            if (task.group in groups and
                    not task.model_item.vpath.startswith("/deployments")):
                raise TaskValidationException('Task for item "{0}" in group '
                        '"{1}" must have an associated model item under'
                        ' "/deployments"'.format(
                            task.model_item.vpath, task.group))

    @et_logged
    def _validate_task_dependencies(self, tasks):
        log.trace.debug("Validating task dependencies")
        combined_groups = [deployment_plan_groups.MS_GROUP]
        for task in tasks:
            log.trace.debug("  task: %s", task)
            for require in task.requires:
                log.trace.debug("    dependency: %s", require)

                if isinstance(require, Task):
                    if task.group != require.group:
                        if task.group in combined_groups \
                                and require.group in combined_groups:
                            if not can_have_dependency_for_validation(task,
                                                                    require):
                                raise TaskValidationException(
                                    "Required task relates to a different "
                                    "node")
                        else:
                            raise TaskValidationException(
                                "Task for item {0} in group {1} and its"
                                " dependent task for item {2} in group"
                                " {3} are in different "
                                "groups".format(
                                    task.model_item.vpath,
                                    task.group,
                                    require.model_item.vpath,
                                    require.group
                                ))
                    elif task.group == deployment_plan_groups.NODE_GROUP:
                        task_node = self._get_task_node(task)
                        require_node = self._get_task_node(require)
                        if task_node != require_node:
                            raise TaskValidationException(
                                "Required task relates to a different node")

                elif isinstance(require, QueryItem):
                    if task.group == deployment_plan_groups.NODE_GROUP:
                        rnode = require.get_node()
                        if not rnode:
                            raise TaskValidationException(
                                "Required item doesn't relate to a node")
                        tnode = self._get_task_node(task)._model_item
                        if rnode != tnode:
                            raise TaskValidationException(
                                "Required item relates to a different node")
                    # Different task group dependency validation
                    for required_task in TaskCollection(tasks).find_tasks(
                            partial_vpath=require.vpath):
                        if GROUP_PRIORITY_INDEX[task.group] < \
                           GROUP_PRIORITY_INDEX[required_task.group]:
                            raise TaskValidationException(
                                "Task for item {0} in group {1} and its"
                                " dependent task for item {2} in group"
                                " {3} are in different "
                                "groups".format(
                                    task.model_item.vpath,
                                    task.group,
                                    required_task.model_item.vpath,
                                    required_task.group
                                ))
                elif isinstance(require, tuple) and len(require) == 2:
                    call_type, call_id = require
                    matches = [other_task for other_task in tasks if
                        isinstance(other_task, ConfigTask) and
                        all((
                            task is not other_task,
                            call_type == other_task.call_type,
                            call_id == other_task.call_id,
                        ))
                    ]
                    # There may be >1 matching ConfigTasks across several nodes
                    if any(match.group != task.group for match in matches):
                        raise TaskValidationException(
                            "Required ConfigTask(s) in different group"
                        )

                else:
                    raise TaskValidationException(
                        "Invalid task dependency: %s" % require)

    def _get_all_nodes(self, tasks):
        nodes = set()
        for task in tasks:
            if isinstance(task, RemoteExecutionTask):
                nodes.update(node._model_item for node in task.nodes)
            elif isinstance(task, CallbackTask):
                node = self._get_task_node(task)
                if node:
                    nodes.add(node._model_item)
            elif isinstance(task, ConfigTask):
                nodes.add(task.node._model_item)
            else:
                raise ValueError("invalid task: %s", task)
        return nodes

    def _get_tasks_from_ordered_task_list(self, otl):
        previous = otl.task_list[0]
        for task in otl.task_list[1:]:
            task.requires.add(previous)
            previous = task
        return otl.task_list

    @et_logged
    def _rewrite_ordered_task_lists(self, original_tasks):
        tasks = []
        for task in original_tasks:
            if isinstance(task, OrderedTaskList):
                tasks.extend(self._get_tasks_from_ordered_task_list(task))
            else:
                tasks.append(task)
        # include required tasks not provided by the plugin
        for task in tasks:
            for require in task.requires:
                if isinstance(require, Task) and require not in tasks:
                    tasks.append(require)
        return tasks

    @et_logged
    def _validate_task_replaces(self, tasks):
        tasks = [task for task in tasks if isinstance(task, ConfigTask)]

        # check if multiple tasks replace one
        all_tasks_replaces = set()
        messages = []
        for task in tasks:
            for (call_type, call_id) in task.replaces:
                key = (task.node.vpath, call_type, call_id)
                if key in all_tasks_replaces:
                    msg = (
                        'There are multiple tasks trying to replace '
                        '("%s", "%s") for node "%s"' %
                        (call_type, call_id, task.node.hostname)
                    )
                    messages.append(msg)
                all_tasks_replaces.add(key)
        if messages:
            raise TaskValidationException(
                    "Task validation errors occurred.", messages)

        plugin_tasks_by_node_ct_ci = create_task_dict_by_node_ct_ci(tasks)

        # check if task replaces other task in same plan
        messages = []
        for task in tasks:
            for (call_type, call_id) in task.replaces:
                if call_type == task.call_type and call_id == task.call_id:
                    continue
                key = (task.node.vpath, call_type, call_id)
                if key in plugin_tasks_by_node_ct_ci:
                    msg = (
                        'A task is trying to replace another task '
                        '("%s", "%s") for node "%s" defined in current plan' %
                        (call_type, call_id, task.node.hostname)
                    )
                    messages.append(msg)
        if messages:
            raise TaskValidationException(
                    "Task validation errors occurred.", messages)

        persisted_tasks_by_node_ct_ci = create_task_dict_by_node_ct_ci(
            self.puppet_manager.all_tasks())

        # check if task replaces non-existent persistent task
        for task in tasks:
            for (call_type, call_id) in task.replaces:
                key = (task.node.vpath, call_type, call_id)
                if key not in persisted_tasks_by_node_ct_ci:
                    msg = (
                        'A task is trying to replace a non-persisted task '
                        '("%s", "%s") for node "%s"' %
                        (call_type, call_id, task.node.hostname)
                    )
                    log.trace.debug(msg)

    @et_logged
    def _get_nodes_to_be_locked(self, tasks, lock_policies=None):
        if lock_policies == None:
            lock_policies = []
        nodes = self._get_all_nodes(tasks)
        nodes_to_be_locked = set()

        # Add node left locked if necessary
        self._add_node_left_locked(lock_policies, nodes_to_be_locked)

        # check all other task nodes
        for node in nodes:
            if not lock_policies:
                if self._is_node_to_be_locked(node):
                    nodes_to_be_locked.add(node)
                continue

            node_lock_policy_results = []
            for lock_policy in lock_policies:
                node_lock_policy_results.append(
                    self._is_node_to_be_locked(node, lock_policy))

            # Give precedence to non-locking policies
            # and only lock nodes if all policies agree
            # on locking
            if False not in node_lock_policy_results:
                nodes_to_be_locked.add(node)

        return nodes_to_be_locked

    def _add_node_left_locked(self, lock_policies, nodes_to_be_locked):
        """
           Adds the node left locked to the set to be locked
           depending on the lock policy.
           The node should be added if there are no lock policies
           or if the policy is CREATE_LOCKS and the node does not
           belong to a list of clusters to be excluded from locking.

        """
        node_left_locked = self.model_manager._node_left_locked()
        if node_left_locked:
            lock_node = False
            if not lock_policies:
                lock_node = True
            else:
                for lock_policy in lock_policies:
                    if lock_policy.getAction() == LockPolicy.CREATE_LOCKS:
                        if not lock_policy.getClusters():
                            lock_node = True
                            break
                        else:
                            cluster = self.model_manager.get_cluster(
                            node_left_locked)
                            if cluster.item_id not in lock_policy.getClusters(
                                ):
                                lock_node = True
                                break

            if lock_node:
                nodes_to_be_locked.add(node_left_locked)

    def _is_node_to_be_locked(self, node, lock_policy=None):
        """
            Returns true if node is to be locked and false
            otherwise.
        """

        cluster = self.model_manager.get_cluster(node)

        if not cluster or \
           ((len(cluster.nodes) <= 1) and lock_policy and \
            (lock_policy.getAction() == LockPolicy.INITIAL_LOCKS)):
            return False

        try:
            if hasattr(cluster, 'ha_manager'):
                if not cluster.ha_manager:
                    return False
        except AttributeError:
            return False

        if node.is_initial():
            if lock_policy and \
            lock_policy.getAction() == LockPolicy.INITIAL_LOCKS:
                return True
            return False

        if cluster.is_initial():
            return False

        if lock_policy and lock_policy.getAction() == LockPolicy.NO_LOCKS:
            return False

        if lock_policy and lock_policy.getAction() == LockPolicy.CREATE_LOCKS:
            if lock_policy.getClusters() and \
                cluster.item_id in lock_policy.getClusters():
                return False
        return True

    @et_logged
    def _split_remote_execution_tasks(self, original_tasks,
                                      nodes_to_be_locked):
        ms = self.model_manager.query("ms")
        # MS doesn't always exists... facepalm
        if ms:
            ms = ms[0]
        else:
            ms = None
        tasks = []
        for task in original_tasks:
            if not isinstance(task, RemoteExecutionTask):
                tasks.append(task)
                continue

            if len(task.nodes) == 1:
                tasks.append(task)
                continue

            for node in set(task.nodes):
                if (
                    (ms and node._model_item.vpath == ms.vpath) or
                    node._model_item in nodes_to_be_locked
                ):
                    new_task = RemoteExecutionTask(
                        [node], task.model_item, task.description,
                        task.agent, task.action, **task.kwargs
                    )
                    new_task.requires = task.requires.copy()
                    new_task.plugin_name = task.plugin_name
                    tasks.append(new_task)
                    task.nodes.remove(node)
            if task.nodes:
                tasks.append(task)
        return tasks

    @property
    def valid_tags(self):
        """
        Set of valid deployment plan tags.
        """
        return DEPLOYMENT_PLAN_TAGS

    def unmatched_group_name(self):
        for rule in DEPLOYMENT_PLAN_RULESET:
            if rule.get('unmatched_tasks', False):
                return rule['group_name']
        return None

    def _task_matches_criteria(self, task, criteria):
        """
        Given a task and a list of criteria dicts, evaluates whether the task
        matches at least one of the criteria dicts in the list. Matching a
        criteria dict means matching every single criterion defined in it.
        :param task: task to be evaluated
        :type task: Task
        :param criteria: criteria against which the task is evaluated
        :type criteria: list or dict
        """
        criteria_list = [criteria] if type(criteria) is dict else criteria

        for criteria in criteria_list:
            log.trace.debug(
                'Begin task %r match against criteria: %s', task, criteria)
            if len(criteria) == 0:
                log.trace.warning('Matching task against empty criteria.')
                break
            task_matches_criteria = True
            for key, expected_value in criteria.iteritems():

                if key == 'task_type':
                    attr_value = task.__class__.__name__
                else:
                    attr_value = task
                    for attr_name in key.split('.'):
                        if attr_name.endswith('()'):
                            attr_name = attr_name[:-2]
                        attr_value = getattr(attr_value, attr_name, None)
                        if callable(attr_value):
                            attr_value = attr_value()

                if attr_value != expected_value:
                    task_matches_criteria = False
                    break

            if task_matches_criteria:
                return True

        return False

    def _setup_task_group(self, task):
        if task.tag_name is not None and task.tag_name not in self.valid_tags:
            log.trace.warning('Invalid task tag name: "{0}"'.\
                    format(task.tag_name))
            task.group = self.unmatched_group_name()
        else:
            for rule in DEPLOYMENT_PLAN_RULESET:
                if self._task_matches_criteria(task, rule.get('criteria', [])):
                    task.group = rule['group_name']
                    break
            if task.group is None:
                task.group = self.unmatched_group_name()

    @et_logged
    def _setup_tasks_groups(self, tasks):
        for task in tasks:
            self._setup_task_group(task)

    def _get_task_boot_group(self, task, lock_policies):

        boot_group = deployment_plan_groups.BOOT_GROUP

        for lock_policy in lock_policies:
            if lock_policy.getAction() == LockPolicy.INITIAL_LOCKS:
                boot_group = deployment_plan_groups.UPGRADE_BOOT_GROUP
        return boot_group

    def _create_plan(self, plan_type, lock_policies=None, node_path=''):
        if lock_policies == None:
            lock_policies = []
        tasks, snapshot_tasks, cleanup_tasks = [], [], []
        lock_tasks = {}
        if plan_type == constants.REBOOT_PLAN:
            return self._create_reboot_plan(lock_policies, node_path)
        if plan_type == constants.DEPLOYMENT_PLAN:
            if self.snapshot_status(
                    constants.UPGRADE_SNAPSHOT_NAME) == 'failed':
                msg = 'Failed snapshot exists when creating the plan'
                log.trace.info(msg)
            tasks = self._create_plugin_tasks('create_configuration')
            tasks = self._rewrite_ordered_task_lists(tasks)
            self._validate_task_replaces(tasks)

            tasks = self._filter_faulty_node_configtasks(tasks)
            removal_tasks = self._create_removal_tasks(tasks)
            cleanup_tasks = [
                t for t in removal_tasks if is_cleanup_task(t)
            ]
            deconfigure_tasks = [
                t for t in removal_tasks if is_deconfigure_task(t)
            ]
            tasks.extend(deconfigure_tasks)
            nodes_to_be_locked = self._get_nodes_to_be_locked(tasks,
                                                              lock_policies)
            tasks = self._split_remote_execution_tasks(
                tasks, nodes_to_be_locked)
            self._setup_tasks_groups(tasks)

            etlog.begin("various arbitrary rules")
            # ensure wait for node/disable netboot tasks require bootpxe tasks
            # and are always in a separate phase (BOOT_GROUP)
            deps_for_node_boot = {}
            for task in tasks:
                if (
                        isinstance(task, CallbackTask) and
                        task.tag_name == deployment_plan_tags.BOOT_TAG
                ):
                    task.group = self._get_task_boot_group(task, lock_policies)
                    deps_for_node_boot.setdefault(
                        task.get_node_for_model_item().hostname, []
                    ).append(task)
            for task in tasks:
                if (
                    isinstance(task, CallbackTask) and
                    task.group == deployment_plan_groups.NODE_GROUP and
                    task.plugin_name == 'bootmgr_plugin' and
                    task.callback.__name__ in ("_wait_for_pxe_boot",
                                               "_wait_for_node",
                                               "_remove_from_cobbler",
                                               "_disable_netboot")
                ):
                    task.group = self._get_task_boot_group(task, lock_policies)
                    if deps_for_node_boot:
                        task.requires |= set(
                            deps_for_node_boot.get(
                                task.get_node_for_model_item().hostname,
                                []
                            )
                        )
            etlog.done()
            self._validate_task_dependencies(tasks)
            self._validate_task_group(tasks)
            lock_tasks = self._create_lock_tasks(nodes_to_be_locked)

        node_left_locked = self.model_manager._node_left_locked()

        if self._snapshot_tasks_needed(plan_type):
            if plan_type in [constants.CREATE_SNAPSHOT_PLAN,
                             constants.REMOVE_SNAPSHOT_PLAN]:
                if node_left_locked:
                    nodes_to_be_locked = set([node_left_locked])
                    for node in nodes_to_be_locked:
                        log.trace.warning(
                            'Node "%s" is locked' % node.hostname)

            snapshot_tasks = self._create_snapshot_tasks(plan_type,
                                                         tasks,
                                                         cleanup_tasks)
            if 'snapshot' in plan_type:
                snapshot_tasks.extend(
                    self._create_removal_tasks([], is_snapshot=True)
                )

        prev_successful_tasks = self._get_prev_successful_tasks()

        plan = None
        if snapshot_tasks:
            etlog.begin("creating snapshot Plan instance")

            tasks = itertools.chain(snapshot_tasks, cleanup_tasks)
            plan_builder = SnapshotPlanBuilder(
                model_manager=self.model_manager,
                plan_type=plan_type.title(),
                tasks=tasks
            )
            plan = plan_builder.build()
            etlog.done()
        else:
            etlog.begin("creating Plan instance")
            plan_builder = PlanBuilder(self.model_manager, tasks,
                                       lock_tasks=lock_tasks)
            plan_builder.previously_successful_tasks = prev_successful_tasks
            phases = plan_builder.build()
            cleanup_tasks = [task for task in cleanup_tasks if not
                task.model_item._model_item.is_instance(base_snapshot_type)]

            if phases or cleanup_tasks or node_left_locked:
                plan = Plan(phases, cleanup_tasks, lock_tasks)
            etlog.done()

        if not plan:
            raise EmptyPlanException()

        return plan

    def _create_reboot_plan(self, lock_policies, node_path):
        tasks = self._get_core_plugin().create_reboot_tasks(self.model_manager,
                                                            node_path)
        tasks = self._rewrite_ordered_task_lists(tasks)
        self._validate_task_replaces(tasks)

        # probably not needed, as reboot plan will only have callback tasks
        tasks = self._filter_faulty_node_configtasks(tasks)
        nodes_to_be_locked = self._get_nodes_to_be_locked(tasks, lock_policies)
        tasks = self._split_remote_execution_tasks(
            tasks, nodes_to_be_locked)
        self._setup_tasks_groups(tasks)
        self._validate_task_dependencies(tasks)
        self._validate_task_group(tasks)

        lock_tasks = self._create_lock_tasks(nodes_to_be_locked)
        node_left_locked = self.model_manager._node_left_locked()
        prev_successful_tasks = self._get_prev_successful_tasks()

        plan = None

        etlog.begin("creating Plan instance")
        plan_builder = PlanBuilder(self.model_manager, tasks,
                                   lock_tasks=lock_tasks)
        plan_builder.previously_successful_tasks = prev_successful_tasks
        phases = plan_builder.build()

        if phases or node_left_locked:
            plan = Plan(phases, [], lock_tasks,
                        plan_type=constants.REBOOT_PLAN)
        etlog.done()

        if not plan:
            raise EmptyPlanException()

        return plan

    def _get_core_plugin(self):
        for name, plugin in self.plugin_manager.iter_plugins():
            if name == 'core_plugin':
                return plugin

    def _get_prev_successful_tasks(self):
        return [task for task in self.puppet_manager.all_tasks()
                    if task.state == constants.TASK_SUCCESS]

    @et_logged
    def _create_lock_tasks(self, nodes_to_be_locked):
        lock_task_creator = LockTaskCreator(
            self.model_manager, self.plugin_manager,
            PluginApiContext(self.model_manager), nodes_to_be_locked
        )
        lock_tasks = lock_task_creator.create_lock_tasks()
        return lock_tasks

    @et_logged
    def _filter_faulty_node_configtasks(self, task_list):
        filtered_tasks = []
        for task in task_list:
            if isinstance(task, ConfigTask):
                if task.node and not task.node.is_for_removal():
                    filtered_tasks.append(task)
            else:
                filtered_tasks.append(task)
        return filtered_tasks

    @et_logged
    def _create_removal_tasks(self, task_list, is_snapshot=False):
        core_generated_removal_tasks = []

        plan_tasks_by_item = create_item_task_dict(task_list)
        puppet_tasks = create_item_task_dict(self.puppet_manager.all_tasks())
        states = set([ModelItem.ForRemoval])

        def _filter_plugin_removal_task(fr_qi):
            removed_tasks = set()
            for removal_task in plan_tasks_by_item[fr_qi.vpath]:
                log.trace.debug(
                    ("Task %r is generated by plugins to effect the "
                    "removal of %s"),
                    removal_task, fr_qi.vpath
                )
                if isinstance(removal_task, ConfigTask) and \
                        removal_task.node.is_for_removal():
                    try:
                        task_list.remove(removal_task)
                        removed_tasks.add(removal_task)
                    except ValueError:
                        # The task has already been filtered out
                        continue
            # Inject a CleanupTask if we've removed all the plugin-generated
            # tasks for that item
            if removed_tasks == set(plan_tasks_by_item[fr_qi.vpath]):
                log.trace.debug(
                    "Replacing task with a CleanupTask"
                )
                core_generated_removal_tasks.append(
                    CleanupTask(fr_qi)
                )

        for fr_model_item in self.data_manager.model.query_by_states(states):
            vpath = fr_model_item.vpath

            # if something is set for_removal and then we run remove_snapshot
            # those items will be removed as well without doing anything.
            # They should stay in for_removal state
            can_be_removed = (not is_snapshot or (is_snapshot and
                fr_model_item.is_instance(base_snapshot_type)))
            if not can_be_removed:
                continue

            fr_query_item = QueryItem(self.model_manager, fr_model_item)

            if vpath in plan_tasks_by_item:
                _filter_plugin_removal_task(fr_query_item)
                continue

            # if vpath in puppet_tasks and puppet_tasks[vpath]:
            #
            # LITPCDS-11125
            # create CleanupTask for _net_task_item_types
            # uses logic from PlanBuilder
            # to be removed when core implements requirement for
            # VCS plugin and plugin is updated
            #
            if (
                vpath in puppet_tasks and puppet_tasks[vpath] and
                not any(
                    fr_model_item.is_instance(it) for
                        it in _net_task_item_types
                )
            ):
                parent_node = self.model_manager.get_node_or_ms(fr_model_item)
                if not parent_node:
                    deconfig_nodes = tuple(
                        task.node for task in puppet_tasks.get(vpath, [])
                    )
                else:
                    deconfig_nodes = (
                            QueryItem(self.model_manager, parent_node),)

                for deconfig_node in deconfig_nodes:
                    if deconfig_node.is_for_removal():
                        log.trace.debug(
                            "Using CleanupTask to remove %s on %r",
                            vpath,
                            deconfig_node
                        )
                        core_generated_removal_tasks.append(
                            CleanupTask(fr_query_item)
                        )
                    else:
                        node_ptasks = []
                        for prev in puppet_tasks[vpath]:
                            if deconfig_node.vpath != prev.node.vpath:
                                continue
                            if self.call_type_and_id_in_tasks(prev, task_list):
                                core_generated_removal_tasks.append(
                                    CleanupTask(fr_query_item)
                                )
                            else:
                                node_ptasks.append(prev)

                        if not node_ptasks:
                            continue
                        task = ConfigTask(
                            deconfig_node, fr_query_item,
                            'Remove Item\'s resource from node "%s" '
                                'puppet manifest' % deconfig_node.hostname,
                                'notify', vpath
                        )
                        for ptask in node_ptasks:
                            task.replaces.add((ptask.call_type, ptask.call_id))
                        core_generated_removal_tasks.append(task)

            elif fr_model_item is not None:
                core_generated_removal_tasks.append(CleanupTask(fr_query_item))
        return core_generated_removal_tasks

    def call_type_and_id_in_tasks(self, p_task, task_list):
        for task in task_list:
            if not isinstance(task, ConfigTask):
                continue
            if p_task.node.vpath != task.node.vpath:
                continue
            if (task.call_type, task.call_id) == \
                    (p_task.call_type, p_task.call_id):
                return True
        return False

    @et_logged
    def _create_plugin_tasks(self, method_name):
        tasks = []
        plugin_api = PluginApiContext(self.model_manager)
        # Safety measure - assign a copy of exclude_nodes to the plugin_api
        plugin_api.exclude_nodes = set(self.exclude_nodes)
        for name, plugin in self.plugin_manager.iter_plugins():
            if not hasattr(plugin, method_name):
                continue
            try:
                new_tasks = self._create_tasks_for_single_plugin(
                        plugin, name, method_name, plugin_api)
                tasks.extend(new_tasks)
            except PluginError:
                raise
            except ViewError as e:
                raise
            except Exception as e:
                log.trace.exception(
                    "Exception creating configuration from "
                    "plugin: %s", name)
                log.trace.debug(e, exc_info=True)
                raise Exception(
                    "Exception creating configuration from "
                    "plugin %s: %s" % (name, str(e)))
        return tasks

    def _create_tasks_for_single_plugin(self, plugin, pname, method_name, api):
        etlog.begin("creating tasks for plugin: %s (%s)", pname, method_name)
        try:
            new_tasks = getattr(plugin, method_name)(api)
        finally:
            etlog.done()

        for task in new_tasks:
            if isinstance(task, OrderedTaskList):
                for _task in task.task_list:
                    _task.plugin_name = pname
                continue
            task.plugin_name = pname

        etlog.begin("checking tasks for plugin: %s", pname)
        try:
            self._check_tasks(plugin, new_tasks)
        finally:
            etlog.done()
        return new_tasks

    def _check_tasks(self, plugin, tasks):
        self._validate_tasks(plugin, tasks)
        self._check_duplicated_tasks(plugin, tasks)
        self._check_task_attributes_datatype(plugin, tasks)

    def _check_task_attributes_datatype(self, plugin, tasks):
        plugin_name = plugin.__class__.__name__
        template = (
            'Error in plugin "%s": Task "%%s" contains invalid '
            'data type ("%%s") in its %%s'
        ) % plugin_name
        all_tasks = self._rewrite_ordered_task_lists(tasks)
        for task in all_tasks:
            for require in task.requires:
                if not isinstance(require, (Task, QueryItem, tuple)):
                    msg = template % (task, type(require), '"requires" set')
                    raise TaskValidationException(msg)
            if isinstance(task, ConfigTask):
                for replace in task.replaces:
                    if not (isinstance(replace, tuple) and len(replace) == 2):
                        msg = template % (task, type(replace), '"replace" set')
                        raise TaskValidationException(msg)

    def _check_duplicated_tasks(self, plugin, tasks):
        plugin_name = plugin.__class__.__name__
        duplicated_tasks = self._find_duplicated_tasks(tasks)

        if duplicated_tasks:
            msg = self._format_duplicated_tasks_err_msg(plugin_name,
                    duplicated_tasks)
            log.trace.error(msg)
            raise NonUniqueTaskException(msg)

    def _format_duplicated_tasks_err_msg(self, plugin_name, duplicated_tasks):
        msg = 'Plugin "{0}" created tasks with duplicated ' \
            '"unique_id" field: '.format(plugin_name)
        for unique_id in duplicated_tasks:
            msg += '[unique_id "{0}" tasks]: ['.format(unique_id)
            for task in duplicated_tasks[unique_id]:
                msg += '"{0}": {1}; '.format(task.description, task)
            msg += ']'
        return msg

    def _find_duplicated_tasks(self, tasks):
        tasks_by_id = self._group_tasks_by_unique_id(tasks)
        self._filter_non_duplicated_tasks(tasks_by_id)
        return tasks_by_id

    def _group_tasks_by_unique_id(self, tasks, tasks_by_id=None):
        if tasks_by_id is None:
            tasks_by_id = dict()
        for task in tasks:
            if isinstance(task, OrderedTaskList):
                self._group_tasks_by_unique_id(task.task_list, tasks_by_id)

            if isinstance(task, ConfigTask) and hasattr(task, 'unique_id'):
                tasks_list = tasks_by_id.setdefault(task.unique_id, [])
                tasks_list.append(task)

        return tasks_by_id

    def _filter_non_duplicated_tasks(self, tasks_by_id):
        for unique_id in tasks_by_id.keys():
            if len(tasks_by_id[unique_id]) == 1:
                del tasks_by_id[unique_id]

    def _get_security_credentials(self):
        """Checks security credentials for each plugin
        """
        for name, plugin in self.plugin_manager.iter_plugins():
            credentials = plugin.get_security_credentials(
                PluginApiContext(self.model_manager))

            for user, service in credentials:
                try:
                    password = CallbackApi(self).get_password(service, user)
                except Exception:
                    raise CorruptedConfFileException(
                        "Error accessing credentials"
                    )
                if not password:
                    log.trace.error(('Not able to find '
                        'credentials for plugin {name}, for service '
                        '"{service}", user "{user}"').format(name=name,
                        service=service, user=user))
                    raise NoCredentialsException((('Not able to find '
                        'credentials for plugin {name}, for service '
                        '"{service}"').format(name=name,
                        service=service)))

    def run_plan_background(self):
        self.sync()
        try:
            from litp.core.worker.tasks import run_plan
            run_plan.s().apply_async()
            retries = 20  # for about 10 seconds
            while (self.plan_state() == self.plan.INITIAL
                and retries > 0):
                self.forget_cached_plan()
                time.sleep(0.5)
                retries -= 1
            return {'success': None}
        except Exception as e:  # pylint:disable=broad-except
            return {'error':  "Error in plan run request enqueue: %s" % (e,)}

    def monitor_plan(self):
        """
        Hook called from celery task run on a schedule.
        Will call _fix_plan if a plan is running but the associated
        celery job is ready (successful or failed)
        """
        plan = self.plan
        if plan:
            celery_task_result = AsyncResult(plan.celery_task_id)
            if self.plan.is_running() and celery_task_result.ready():
                log.trace.info("Monitor detected running plan and %s worker"
                    % (celery_task_result.status))
                self._fix_plan(plan)


class ExecutionManager(ExecutionManagerNextGen):
    def __init__(self, model_manager, *args, **kwargs):
        super(ExecutionManager, self).__init__(model_manager, *args, **kwargs)
        self._plan = None
        self.data_manager = model_manager.data_manager

    @property
    def plan(self):
        return self._plan

    @plan.setter
    def plan(self, value):  # pylint: disable=arguments-differ
        self._plan = value
