##############################################################################
# COPYRIGHT Ericsson AB 2013
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################


import collections
import itertools
import os
import re
import shutil
import stat
import time
import fcntl
from grp import getgrnam
from pwd import getpwnam

from litp.core.persisted_task import PersistedTask
from litp.core.base_manager import BaseManager
from litp.core.event_emitter import EventEmitter
from litp.core.exceptions import McoFailed, FailedTasklessPuppetEvent
from litp.core.puppet_manager_templates import PuppetManagerTemplates
from litp.core.litp_logging import LitpLogger
from litp.core.constants import (
    TASK_INITIAL, TASK_RUNNING, TASK_FAILED, TASK_SUCCESS, TASK_STOPPED
)
from litp.core.rpc_commands import (
        PuppetMcoProcessor, has_errors
)
from litp.enable_metrics import apply_metrics as metrics
from litp.metrics import time_taken_metrics
from litp.core.puppetdb_api import PuppetDbApi


log = LitpLogger()


class PuppetManagerNextGen(EventEmitter, BaseManager):
    PUPPET_RUN_CONCURRENCY = 10
    PUPPET_RUN_WAIT_BETWEEN_RETRIES = 5  # seconds
    PUPPET_APPLYING_WAIT_BETWEEN_RETRIES = 2
    PUPPET_RUN_COMMAND_TIMEOUT = 10  # seconds
    PUPPET_RUN_TOTAL_TIMEOUT = 900  # seconds
    PUPPET_LOCK_TIMEOUT = 1980  # seconds
    PUPPET_TASKLESS_FAILURE_RETRIES = 300
    DEFAULT_GROUP = "puppet"
    CELERY_USER = "celery"

    Feedback = collections.namedtuple(
        'Feedback', (
            'hostname', 'phase_config_version', 'resource_reports',
            'failed_taskless_event'
        )
    )

    def __init__(self, model_manager, litp_root_dir=None):
        super(PuppetManagerNextGen, self).__init__()
        self.model_manager = model_manager
        self.phase_complete = False
        self.phase_stopped = False
        self.phase_successful = False
        self.phase_tasks = set()
        self._hosts_in_phase = None
        self.litp_root_dir = litp_root_dir or "/opt/ericsson/nms/litp"
        self._processed_nodes = set()
        self._reported_phase_tasks = set()
        self._processing_nodes = set()
        self.killed = False
        self._task_backup = collections.defaultdict(list)
        self.check_timeout = True
        self.check_freq = True
        self.mco_processor = PuppetMcoProcessor()
        self._sleep_if_not_killed = self.mco_processor.smart_sleep
        self.api = PuppetDbApi()
        self.phase_config_version = None

    @property
    def node_tasks(self):
        node_tasks = collections.defaultdict(list)
        for persisted_task in self.data_manager.get_persisted_tasks():
            hostname = persisted_task.hostname
            task = persisted_task.task
            task.initialize_from_db(self.data_manager, self.model_manager)
            node_tasks[hostname].append(task)
        return node_tasks

    def _get_node_tasks_for_hostname(self, hostname):
        tasks = []
        for persisted_task in self.data_manager.get_persisted_tasks_for_node(
                hostname):
            task = persisted_task.task
            task.initialize_from_db(self.data_manager, self.model_manager)
            tasks.append(task)
        return tasks

    def _update_persisted_tasks_for_node(self, hostname, tasks):
        ptasks = []
        for seq_id, task in enumerate(tasks):
            ptask = PersistedTask(hostname, None, seq_id)
            ptask.task_id = task._id
            ptasks.append(ptask)
        self.data_manager.update_persisted_tasks(hostname, ptasks)

    def _open_file(self, filename, mode="w"):
        return open(filename, mode)

    def _remove_file(self, filename):
        return os.remove(filename)

    def _exists(self, filename):
        return os.path.exists(filename)

    def manifest_file(self, filepath):
        return os.path.join(self.manifest_dir(), filepath)

    @property
    def default_manifests_dir(self):
        return os.path.join(self.litp_root_dir,
                            "etc/puppet/modules/litp/default_manifests/")

    def manifest_dir(self, manifest_dir="plugins"):
        return os.path.join(
            self.litp_root_dir, "etc/puppet/manifests/", manifest_dir)

    def config_version_file(self):
        return os.path.join(
            self.litp_root_dir,
            "etc/puppet/litp_config_version")

    def _makedirs(self, dirpath):
        os.makedirs(dirpath)

    def _fchmod(self, file_instance, mode):
        os.fchmod(file_instance.fileno(), mode)

    def _fchown(self, file_instance):
        try:
            os.fchown(file_instance.fileno(),
                      getpwnam(PuppetManagerNextGen.CELERY_USER).pw_uid,
                      getgrnam(PuppetManagerNextGen.DEFAULT_GROUP).gr_gid)
        except KeyError as e:
            log.trace.warning("Could not set file ownership of file %s. %s" %
                              (file_instance.name, str(e)))

    def _write_file(self, filepath, contents):
        dirpath = os.path.dirname(os.path.abspath(filepath))
        if not self._exists(dirpath):
            self._makedirs(dirpath)
        pp_file = self._open_file(self.manifest_file(filepath))
        try:
            fcntl.flock(pp_file, fcntl.LOCK_EX)
            try:
                self._fchmod(
                    pp_file,
                    (stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP)
                )
                self._fchown(pp_file)
                pp_file.write(contents)
                pp_file.flush()
                os.fsync(pp_file.fileno())
            finally:
                fcntl.flock(pp_file, fcntl.LOCK_UN)
        finally:
            pp_file.close()

    def all_tasks(self):
        '''
        Return an iterator for all :class:`litp.core.task.ConfigTask`
        instances known to the Puppet Manager.
        '''

        return itertools.chain.from_iterable(self.node_tasks.values())

    def has_failures(self):
        return self._any_tasks_failed(self.all_tasks())

    def _get_required_task_uids(self, task, task_list, removed_task_id_set,
            task_dict):
        required_uids = set()
        queue = collections.deque(task._requires)

        while queue:
            required_task = task_dict.get(queue.popleft())
            if required_task is None:
                continue
            if required_task._id not in removed_task_id_set:
                required_uids.add(required_task.unique_id)
            else:
                queue.extend(required_task._requires)

        return required_uids

    def _update_tasks_requires(self, task_list, removed_list,
            removed_task_id_set, task_dict):
        requires_set = set(removed_list)
        for task in task_list:
            if task._id in removed_task_id_set:
                continue
            if not (task._requires or task.requires):
                continue

            task._requires = self._get_required_task_uids(
                task, task_list, removed_task_id_set, task_dict)
            task.requires -= requires_set

    def _rewrite_persisted_tasks(self, match):
        '''
        Update the persisted tasks for all nodes at the end of a plan so that
        tasks matching the ``match`` callback are filtered out.

        :param match: A callback function taking a ConfigTask instance as
            argument and returning True if that task is to be filtered out of
            the persisted tasks.
        :type match: callable

        :return: A tuple comprising the set of all ConfigTasks filtered out of
            the persisted tasks and the set of hostnames for the nodes on which
            the set of persisted tasks was updated.
        :rtype: tuple
        '''
        task_dict = {}  # {task.unique_id: task}
        removed_task_id_set = set()
        all_removed_tasks = set()
        # safely remove from task lists items that match filter
        node_tasks = self.node_tasks  # prevents db query at each iteration

        updated_persisted_tasks_hostnames = set()
        for hostname, tasks_in_manifest in node_tasks.iteritems():
            removed_list = []

            for task in tasks_in_manifest:
                task_dict[task.unique_id] = task
                # Build set of uid strings to comapare instead of task objects
                if match(task):
                    removed_list.append(task)
                    removed_task_id_set.add(task._id)

            if not removed_list:
                continue
            all_removed_tasks |= set(removed_list)

            self._update_tasks_requires(
                tasks_in_manifest,
                removed_list,
                removed_task_id_set,
                task_dict
            )
            # Filter out tasks matching the removal selector and persist the
            # resulting task list
            filtered_tasks = [task for task in tasks_in_manifest if
                task._id not in removed_task_id_set]
            self._update_persisted_tasks_for_node(hostname, filtered_tasks)

            # We've made changes to the persisted tasks for this node, we must
            # ensure its manifest is rewritten and a catalog run is performed
            # on it at the end of the plan
            updated_persisted_tasks_hostnames.add(hostname)
        return updated_persisted_tasks_hostnames, all_removed_tasks

    def _backup_manifests(self):
        try:
            to_dir = self.manifest_dir("plugins.failed")
            from_dir = self.manifest_dir()
            if self._exists(to_dir):
                shutil.rmtree(to_dir)
            if self._exists(from_dir):
                shutil.copytree(from_dir, to_dir)
        except OSError as e:
            log.trace.info("Error occurred while backing up manifests: %s",
                    e.strerror)

    def _get_backup_task_by_task_id(self, task_id):
        return self.data_manager.get_task(task_id)

    def restore_backed_up_tasks(self):
        """Update the persisted tasks in the database after a puppet phase ends

        Iterate over the current phases node(s) creating a list of all tasks
        to be persisted. If a task has failed, remove it and replace it with
        a previously successful version, if it exists, fixing the manifest.
        """
        log.trace.debug("restoring backed up tasks")
        node_tasks = self.node_tasks  # prevents db query at each iteration
        for hostname in self._processing_nodes:
            tasks_to_persist = []
            for task in node_tasks[hostname]:
                if TASK_FAILED == task.state:
                    if task._id in self._task_backup:
                        tasks_to_persist.extend([
                            self._get_backup_task_by_task_id(task_id)
                            for task_id in self._task_backup[task._id]
                        ])
                else:
                    tasks_to_persist.append(task)
            # This function will delete all persisted tasks for a node first
            self._update_persisted_tasks_for_node(hostname, tasks_to_persist)
        self._task_backup.clear()

    def configtask_removal_selector(self, task):
        '''
        Determines whether a given ConfigTask should be taken out of the
        PuppetManager instance's node_tasks dictionary at the end of a plan, as
        well as filtered out of the dependencies for tasks in node_tasks.

        :param task: The Puppet task whose continued inclusion in node_tasks
            will be evaluated.
        :type task: litp.core.task.ConfigTask

        :return: True if the task is to be removed from node_tasks, else False
        :rtype: bool
        '''

        # A ConfigTask that was being applied by Puppet when the plan was
        # stopped should be taken out of node_tasks as it isn't
        # successfully applied
        def is_stopped_task(task):
            return task.state == TASK_STOPPED

        # A successful ConfigTask should be taken out of node_tasks at the
        # end of a plan if it is transient, ie if either:
        def is_successful_transient_task(task):
            # When resuming execution of a failed phase, it is possible to have
            # previously successfully executed tasks whose model item has been
            # deleted from the model; these should return based on task success
            if isinstance(task.model_item, basestring):
                return task.state == TASK_SUCCESS
            return task.state == TASK_SUCCESS and any((
                # ...it's been generated as a non-persisted task
                task.persist == False,
                # ...its model item has successfully transitioned from
                # ForRemoval to Removed and no item in its progeny remains in
                # the ForRemoval state.
                task.model_item._model_item.is_removed() and not any(
                    item.is_for_removal() for item in
                    self.model_manager.query_descends(
                        task.model_item._model_item
                    )
                ),
            ))

        return any((
            is_stopped_task(task),
            is_successful_transient_task(task),
        ))

    def _actual_cleanup(self, decommissioned, cleanup_tasks, failure_nodes):
        '''
        If necessary, backs up, updates or deletes Puppet manifests.

        :param decommissioned: A set of node model items for which the Puppet
            manifests will be destroyed and persisted task information
            discarded.
        :type decommissioned: set of
            :class:`litp.core.model_item.ModelItem`

        :param cleanup_tasks: A list of all core-generated cleanup tasks in
            the plan
        :type cleanup_tasks: list of :class:`litp.core.task.CleanupTask`

        :param failure_nodes: A set of hostnames of nodes with
            failed ConfigTasks from the current plan
        :type failure_nodes: set
        '''

        # Make a copy of the manifests if any ConfigTasks have failed
        if failure_nodes:
            self._backup_manifests()

        updated_persisted_tasks_hostnames, removed_config_tasks = \
                self._rewrite_persisted_tasks(
            self.configtask_removal_selector
        )

        all_removed_resources = removed_config_tasks | set(
            cleanup_task for cleanup_task in cleanup_tasks if
                cleanup_task.state == TASK_SUCCESS
        )

        # A set of node model items that are left in the ``ForRemoval`` state
        # at the end of a plan and for which manifests cannot be removed nor
        # catalog runs performed
        for_removal_nodes = set(
            n for n in self.model_manager.get_all_nodes() if n.is_for_removal()
        )

        # Do not perform a Puppet catalog run on nodes that have reached the
        # Removed state or that are still in the ForRemoval state
        apply_removal_nodes = updated_persisted_tasks_hostnames - set(
            node.hostname for node in (decommissioned | for_removal_nodes)
        )

        if (failure_nodes or decommissioned or removed_config_tasks) and \
                not self.killed:
            log.trace.debug("Puppet cleanup - removing resources for:"
                    " %s on %s",
                    all_removed_resources, apply_removal_nodes)
            self.apply_removal(apply_removal_nodes | failure_nodes)

        # NOTE It's not appropriate to remove manifests for nodes that are
        # still in the ForRemval state. This is only OK for nodes that are in
        # the Removed state
        # delete manifest files for removed nodes
        log.trace.debug(
            "Puppet cleanup - removing nodes: %s", decommissioned
        )
        for node in decommissioned:
            pp_file = self.manifest_file("%s.pp" % (node.hostname).lower())
            if self._exists(pp_file):
                self._remove_file(pp_file)
            # Delete deconfigured node 'hostname' from persisted tasks
            if node.hostname in self.node_tasks:
                self.data_manager.delete_persisted_tasks_for_node(
                    node.hostname)

    def _prepare_restore_cleanup(self, initial_nodes):
        '''
        Causes the Puppet manifests for the nodes passed as argument to be
        deleted and the persisted task data for these nodes to be discarded.
        '''

        self._actual_cleanup(initial_nodes, [], set())

    def cleanup(self, cleanup_tasks, failure_nodes):
        # A set of node model items that have successfully entered the
        # ``Removed`` state at the end of a plan and for which manifests will
        # be removed
        removed_nodes = set(
            n for n in self.model_manager.get_all_nodes() if n.is_removed()
        )
        self._actual_cleanup(
            removed_nodes,
            cleanup_tasks,
            failure_nodes
        )

    def apply_removal(self, cleanup_nodes):
        cleanup_hostnames = list(cleanup_nodes)

        log.event.info("Cleaning stale Puppet agent lock files")
        ret = self.mco_processor.puppetlock_clean(cleanup_hostnames)
        if has_errors(ret):
            log.event.error("An error occurred during LITP's Puppet clean-up "
                    "before the manifests were written.")
            return

        log.event.info("Disabling Puppet")
        ret = self.mco_processor.disable_puppet(cleanup_hostnames)
        if has_errors(ret):
            log.event.error("An error occurred during LITP disabling Puppet "
                    "before the manifests were written.")
            return

        try:
            self._check_puppet_status(cleanup_hostnames)
        except McoFailed:
            log.event.error("An error occurred during LITP checking puppet "
                    "status before the manifests were written.")
            return

        self._write_templates(cleanup_hostnames)

        log.event.info("Clear puppet cache")
        ret = self._clear_puppet_cache([self.get_ms_hostname()])
        if has_errors(ret):
            log.event.error("An error occurred during LITP's Puppet clean-up "
                            "after the manifests were written.")
            return

        log.event.info("Enabling Puppet")
        ret = self.mco_processor.enable_puppet(cleanup_hostnames)
        if has_errors(ret):
            log.event.error("An error occurred during LITP's Puppet clean-up "
                    "after the manifests were written.")
            return

        log.event.info("Running Puppet")
        ret = self.mco_processor.runonce_puppet(cleanup_hostnames)
        if has_errors(ret):
            log.event.error("An error occurred during LITP's Puppet clean-up "
                    "after the manifests were written.")
            return

    def _all_tasks_suceeded(self, task_iterable):
        '''
        Returns ``True`` if all :class:`litp.core.task.ConfigTask` instances
        in ``task_iterable`` are successful, else returns ``False``.
        Returns ``False`` when ``task_iterable`` is empty.

        :param task_iterable: An iterable sequence of
            :class:`litp.core.task.ConfigTask` instances
        :rtype: bool
        '''

        # The builtin all() function returns True for an empty iterable which
        # is not what we want here.
        empty_iterable = True
        for task in task_iterable:
            empty_iterable = False
            if task.state != TASK_SUCCESS:
                return False
        return True if not empty_iterable else False

    def _any_tasks_failed(self, task_iterable):
        '''
        Returns ``True`` if at least one :class:`litp.core.task.ConfigTask`
        instance in ``task_iterable`` has failed, else returns ``False``.
        Returns ``False`` when ``task_iterable`` is empty.

        :param task_iterable: An iterable sequence of
            :class:`litp.core.task.ConfigTask` instances
        :rtype: bool
        '''

        return any(task.state == TASK_FAILED for task in task_iterable)

    def item_by_path(self, vpath):
        return self.model_manager.get_item(vpath)

    # prefixes in task identifiers found in puppet feedback
    FBACK_TASK_PREF = 'task_'
    FBACK_UUID_PREF = 'tuuid_'

    def _build_report(self, task_list):
        '''
        Converts a comma-separated representation of the status of Puppet
        resources in the POST request sent by landscape.rb into a dictionary
        using a 2-tuple of every Puppet resource's ``unique_id`` and ``uuid``
        tag (if present) as keys and the string representation of the
        resources' success or failure as value.

        :return: A dictionary with a tuple of every Puppet resource's
            ``unique_id`` and ``uuid`` tag (if present) as keys and the string
            representation of the resources' success or failure as values
        :rtype: dict
        '''

        report = dict()
        # task_list is a string of comma separated key-value pairs in the
        # following format:
        # litp_feedback:task_$UNIQUE_ID:tuuid_$UUID=success
        for task in task_list.split(","):
            if "=" in task:
                task_id, success = task.split("=")
                try:
                    _, unique_id, uuid = task_id.split(":")
                    unique_id = unique_id[len(self.FBACK_TASK_PREF):]
                    uuid = uuid[len(self.FBACK_UUID_PREF):]
                    report[(unique_id, uuid)] = success
                except ValueError:
                    _, unique_id = task_id.split(":")
                    unique_id = unique_id[len(self.FBACK_TASK_PREF):]
                    report[(unique_id,)] = success
        return report

    def _guess_node_from_error(self, error):
        m = re.search(r'.*on node (?P<node_fqdn>\S+)$', error)
        if m:
            node_fqdn = m.group('node_fqdn')
            node = node_fqdn.split('.')[0]
            return node
        return

    def _feedback_to_state(self, feedback):
        '''Map Puppet feedback values to task state'''
        state_map = {
            'success': TASK_SUCCESS,
            'fail': TASK_FAILED
        }
        if feedback in state_map:
            return state_map[feedback]
        else:
            log.trace.debug(
                "Puppet feedback status not in %s: %s",
                state_map.keys(), feedback)
            return feedback

    @staticmethod
    def _format_report_for_logs(report):
        return format_puppet_report(report)

    def _process_feedbacks(self, puppet_phase):
        # Hostnames may be mixed-case, certnames may not
        for hostname in self._processing_nodes:
            feedback = self.api.check_for_feedback(hostname,
                    self.phase_config_version, puppet_phase)
            if feedback:
                self._process_feedback(PuppetManager.Feedback(*feedback))

    def _process_feedback(self, feedback):
        '''
        Process a feedback tuple in the queue.
        '''

        formatted_report = self._format_report_for_logs(
            feedback.resource_reports
        )
        log.trace.debug(
            "Received feedback for node %s: %s",
            feedback.hostname,
            formatted_report
        )

        log.trace.debug(
            "Processing feedback for node %s begins", feedback.hostname
        )
        time_before_feedback = time.time()
        ret = self._puppet_feedback(feedback)
        time_after_feedback = time.time()
        log.trace.debug(
            "Processing feedback for node %s is done", feedback.hostname)
        log.trace.debug(
            "Feedback processed in %s seconds",
            int(time_after_feedback - time_before_feedback))
        return ret

    def _puppet_feedback(self, feedback):
        if self.phase_complete:
            log.trace.debug('Puppet feedback - phase already complete')
            return

        hostname = feedback.hostname.split('.')[0]
        node_names = [name.lower() for name in self._hosts_in_phase]
        if hostname not in set(node_names):
            log.trace.debug(
                'Puppet feedback - hostname %s not in node list %s',
                hostname, node_names)
            return

        all_resources_report = self._build_report(feedback.resource_reports)
        new_reported_tasks = self.process_report(all_resources_report)
        if not new_reported_tasks:
            log.trace.debug('Puppet feedback - no new_reported_tasks')
            return

        tasks_states_pairs = self._get_tasks_states_pairs(
            new_reported_tasks, all_resources_report
        )
        self.emit('puppet_feedback', tasks_states_pairs)
        # LITPCDS-6168 - _reported_phase_tasks were updated with tasks before
        # the timestamp check on puppet report - if another plan had been run
        # before, tasks with matching id would be added to the set and then the
        # whole report would be rejected by ExecutionManager
        # _reported_phase_tasks seems now to be redundant - candidate for
        # removal
        self._reported_phase_tasks.update(new_reported_tasks)

        # Since we'll only receive one report for this node in a given phase,
        # we must mark any tasks missing from the report as failed
        for t in self.phase_tasks:
            if t.node.hostname != hostname:
                continue
            if t.state == TASK_RUNNING:
                t.state = TASK_FAILED

        if feedback.failed_taskless_event:
            raise FailedTasklessPuppetEvent

        if (self.phase_tasks == self._reported_phase_tasks and
                self._all_nodes_processed()):
            if all(task.state == TASK_SUCCESS for task in self.phase_tasks):
                self.complete_phase(True)
            elif all(task.state != TASK_RUNNING for task in self.phase_tasks):
                self.complete_phase(False)

    def process_report(self, report):
        '''
        :return: A set of :class:`~litp.core.task.ConfigTask` comprising all
            tasks in the report that appear in the current phase.
        :rtype: set
        '''
        tasks = set()
        for task_id in report:
            # task_id is a tuple consisting of unique_id (not so unique)
            # and uuid
            for task in self.phase_tasks:
                if task_id[0] == task.unique_id:
                    if len(task_id) > 1 and task_id[1] != task.uuid:
                        continue
                    tasks.add(task)
                    self._processed_nodes.add(task.get_node().hostname)
        return tasks

    def _get_tasks_states_pairs(self, phase_tasks_in_report, report):
        def _unique_id_and_uuid(task_ids):
            task_id = task_ids[0]
            try:
                task_uuid = task_ids[1]
            except IndexError:
                task_uuid = None
            return task_id, task_uuid

        pairs = []
        task_lookup = {}
        for task in phase_tasks_in_report:
            if task.unique_id not in task_lookup:
                task_lookup[task.unique_id] = {}
            task_lookup[task.unique_id][task.uuid] = task

        for report_task_ids, feedback in report.iteritems():
            task_id, task_uuid = _unique_id_and_uuid(report_task_ids)
            feedback = self._feedback_to_state(feedback)

            try:
                matches = task_lookup[task_id]
                if task_uuid:
                    task = matches[task_uuid]
                else:
                    continue

            except KeyError:
                # This is a resource report for a previously applied task
                continue

            if task.state in (TASK_INITIAL, TASK_RUNNING, TASK_FAILED):
                pairs.append((task, feedback))
        return pairs

    def _all_nodes_processed(self):
        return self._processing_nodes.issubset(self._processed_nodes)

    def complete_phase(self, success):
        log.trace.debug('puppet phase completed (success=%s)', success)
        self.phase_successful = success
        # phase_tasks needs to be reset. If after the current phase a new
        # one starts and it is made only of CallbackTasks then the execution
        # manager will wrongly add these tasks from the previous phase to the
        # processed task list, since process_report will get confused
        self.phase_tasks = set()
        self._reported_phase_tasks = set()
        # unlock waiting thread
        self.phase_complete = True

    def _puppet_poll(self, node_hostnames, next_poll, poll_freq,
            poll_count, original_poll_count):
        if not self.check_freq:
            return next_poll, poll_count
        next_poll -= 0.5
        if next_poll <= 0:
            next_poll = poll_freq
            if not self._is_puppet_alive(node_hostnames):
                poll_count -= 1
                if poll_count <= 0:
                    if not self.phase_complete:
                        msg = ("Maximum poll count reached. Puppet not "
                            "applying configuration. Failing running tasks"
                        )
                        log.trace.error(msg)
                        self.emit('puppet_timeout', self.phase_tasks)
                        self.complete_phase(success=False)
            else:
                poll_count = original_poll_count
        return next_poll, poll_count

    def _finish_wait_for_phase(self, timeout, poll_count):
        if not self.phase_complete:
            if self.killed:
                log.trace.info("Puppet phase killed. Stop running tasks")
            if self.check_timeout and timeout <= 0:
                log.trace.error("Puppet phase timeout. Failing running tasks")
                self.emit('puppet_timeout', self.phase_tasks)
            self.complete_phase(success=False)

    def wait_for_phase(self, puppet_phase, timeout=43200,
                        poll_freq=60, poll_count=5):
        node_hostnames = list(set([task.node.hostname for task in puppet_phase
                          if not task.has_run()]))
        self.check_timeout = True if timeout != 0 else False
        self.check_freq = True if poll_freq != 0 else False

        next_poll = poll_freq
        original_poll_count = poll_count
        failed_taskless_retries = self.PUPPET_TASKLESS_FAILURE_RETRIES

        while not self.phase_complete \
                and (not self.check_timeout or timeout > 0) \
                and not self.killed and node_hostnames:

            try:
                self._process_feedbacks(puppet_phase)
            except FailedTasklessPuppetEvent:
                if failed_taskless_retries == 0:
                    log.trace.info('Failing phase due to taskless failed '
                        'event')
                    incomplete_tasks = [
                        task for task in puppet_phase if not task.has_run()
                    ]
                    for task in incomplete_tasks:
                        task.state = TASK_FAILED
                    if incomplete_tasks:
                        self.complete_phase(False)
                else:
                    failed_taskless_retries -= 1
                    log.trace.info('Taskless failed event detected. %d '
                        'retries left', failed_taskless_retries)

            if self.phase_complete:
                break

            node_hostnames = [host for host in node_hostnames \
                    if host not in self._processed_nodes]

            next_poll, poll_count = self._puppet_poll(node_hostnames,
                    next_poll, poll_freq,  poll_count, original_poll_count)

            self._sleep(0.5)
            timeout -= 0.5

        self._finish_wait_for_phase(timeout, poll_count)
        return self.phase_successful

    def _sleep(self, seconds):
        time.sleep(seconds)

    def set_report_callback(self, callback):
        pass

    def add_phase(self, task_list, phase_id):
        phase_no = phase_id + 1
        log.trace.debug('adding puppet phase %s', phase_no)
        self.phase_stopped = False
        self.phase_complete = False
        self.phase_tasks = set(task_list)
        self._processed_nodes = set()
        self._processing_nodes = set(t.get_node().hostname for t in task_list)
        # check for tasks which hash to the same value
        if len(task_list) != len(self.phase_tasks):
            log.trace.info('add phase %s tasks has duplicate hashs', phase_no)
            id_set = set(id(t) for t in self.phase_tasks)
            discarded = [t for t in task_list if id(t) not in id_set]
            log.trace.debug(
                'add phase %s discarded tasks %s', phase_no, discarded)
        # check for tasks which have the same unique_id
        uid_dict = collections.defaultdict(list)
        for t in task_list:
            uid_dict[t.unique_id].append(t)

        uid_dups = [(k, v) for k, v in uid_dict.items() if len(v) > 1]

        if any(uid_dups):
            for k, tasks in uid_dups:
                dup_err = []

                desc = ["'{0}'".format(t.description) for t in tasks]

                dup_err.append("{0} with the same unique_id '{1}'"\
                               .format(', '.join(desc), k))

                err_msg = "During add phase '{0}', found tasks {1}"\
                          .format(phase_no, ', '.join(dup_err))

                log.trace.warning(err_msg)

        hosts_in_phase = set()
        self._hosts_in_phase = hosts_in_phase
        for task in task_list:
            node = task.get_node()
            hosts_in_phase.add(node.hostname)

        # using OrderedDict to make sure that:
        #   1. (call_type, call_id) will be unique (hint: "dict")
        #   2. original order of tasks will be preserved (hint: "ordered")

        persisted_tasks = {}
        for hostname in hosts_in_phase:
            persisted_node_tasks = collections.OrderedDict()
            persisted_tasks[hostname] = persisted_node_tasks
            node_tasks = self._get_node_tasks_for_hostname(hostname)
            for task in node_tasks:
                key = (task.call_type, task.call_id)
                persisted_node_tasks[key] = task

        for task in task_list:
            node = task.get_node()
            persisted_node_tasks = persisted_tasks[node.hostname]

            key = (task.call_type, task.call_id)
            for rkey in task.replaces:
                if rkey in persisted_node_tasks:
                    # backup replaced task
                    self._task_backup[task._id].append(
                        persisted_node_tasks[rkey]._id)
                    # delete replaced task
                    del persisted_node_tasks[rkey]

            if key in persisted_node_tasks:
                # backup persisted task
                self._task_backup[task._id].append(
                    persisted_node_tasks[key]._id)

            # add task or overwrite persisted task in place
            persisted_node_tasks[key] = task

        for hostname in hosts_in_phase:
            self._update_persisted_tasks_for_node(
                hostname, persisted_tasks[hostname].itervalues())

        self.emit('puppet_phase_start', task_list, phase_id)

    def check_mco_result(self, mco_result):
        if has_errors(mco_result):
            if not self._all_tasks_suceeded(self.all_tasks()):
                raise McoFailed("Mco command failed", result=mco_result)

    def apply_nodes(self):
        try:
            return self._apply_nodes()
        except McoFailed as e:
            log.event.error(str(e) + "; " + str(e.result))
            self.emit("on_mco_error", self.phase_tasks)
            return e.result

    def disable_puppet_on_hosts(self, hostnames=None, task_state=TASK_RUNNING):
        if not hostnames:
            (mixed_phase, ms_hostname, node_hostnames, all_hostnames) = \
                                          self._get_phase_hostnames(task_state)
            if mixed_phase:
                hostnames = all_hostnames
            else:
                hostnames = node_hostnames if node_hostnames else [ms_hostname]

        log.event.info("Disabling Puppet")
        with time_taken_metrics(metrics.disable_puppet_in_phase_metric):
            self.check_mco_result(self.mco_processor.disable_puppet(hostnames))

    def _get_phase_hostnames(self, task_state=TASK_RUNNING):
        ms_hostname = self.get_ms_hostname()
        has_task_for_ms = False
        node_hostnames = set()
        for phase_task in self.phase_tasks:
            if phase_task.state == task_state:
                if phase_task.node.hostname == ms_hostname:
                    has_task_for_ms = True
                else:
                    node_hostnames.add(phase_task.node.hostname)
        node_hostnames = list(node_hostnames)

        mixed_phase = has_task_for_ms and node_hostnames
        all_hostnames = node_hostnames + [ms_hostname]

        return mixed_phase, ms_hostname, node_hostnames, all_hostnames

    def _apply_nodes(self):
        if self.phase_complete or self.phase_stopped or self.killed:
            log.trace.info(
                "Not applying Puppet manifest! "
                "phase_complete: %s, phase_stopped: %s, killed: %s",
                self.phase_complete, self.phase_stopped, self.killed
            )
            return

        (mixed_phase, ms_hostname,
                   node_hostnames, all_hostnames) = self._get_phase_hostnames()

        if mixed_phase:
            # phase has tasks for BOTH ms and nodes
            self.disable_puppet_on_hosts(hostnames=all_hostnames)

            log.event.info("Stopping puppet applying")
            self._stop_puppet_applying(all_hostnames)

            log.event.info("Cleaning stale Puppet agent lock files")
            self.check_mco_result(self.mco_processor.puppetlock_clean(
                all_hostnames))

            log.event.info("Writing templates")
            self._write_templates(all_hostnames)

            log.event.info("Clearing puppet cache")
            self.check_mco_result(self._clear_puppet_cache([ms_hostname]))

            log.event.info("Enabling Puppet on nodes")
            self.check_mco_result(
                    self.mco_processor.enable_puppet(node_hostnames))

            log.event.info("Running Puppet on nodes")
            self.check_mco_result(
                    self.mco_processor.runonce_puppet(node_hostnames))

            log.event.info("Waiting 30 seconds to enable Puppet on MS")
            # see http://jira-nam.lmera.ericsson.se/browse/LITPCDS-9393
            # it is not meant to be a final solution whatsoever
            self._sleep(30)

            log.event.info("Enabling Puppet on MS")
            self.check_mco_result(
                    self.mco_processor.enable_puppet([ms_hostname]))

            log.event.info("Running Puppet on MS")
            self.check_mco_result(
                    self.mco_processor.runonce_puppet([ms_hostname]))

        else:
            # Phase has tasks for either ms OR nodes
            hostnames = node_hostnames if node_hostnames else [ms_hostname]

            self.disable_puppet_on_hosts(hostnames=hostnames)

            log.event.info("Stopping Puppet applying")
            self._stop_puppet_applying(hostnames)

            log.event.info("Cleaning stale Puppet agent lock files")
            self.check_mco_result(
                self.mco_processor.puppetlock_clean(hostnames))

            log.event.info("Writing templates")
            self._write_templates(hostnames)

            log.event.info("Clearing Puppet cache")
            self.check_mco_result(self._clear_puppet_cache([ms_hostname]))

            log.event.info("Enabling Puppet")
            self.check_mco_result(self.mco_processor.enable_puppet(hostnames))

            log.event.info("Running Puppet")
            self.check_mco_result(self.mco_processor.runonce_puppet(hostnames))

    def _set_task_redundant_requires(self, all_node_tasks):
        for hostname, node_tasks in all_node_tasks.iteritems():

            node_tasks_by_unique_id = {}
            for task in node_tasks:
                node_tasks_by_unique_id[task.unique_id] = task

            for task in node_tasks:
                task._redundant_requires = set()
                for req_id in task._requires:
                    req_task = node_tasks_by_unique_id.get(req_id)
                    if not req_task:
                        continue
                    for req_req_id in req_task._requires:
                        if req_req_id not in task._requires:
                            continue
                        task._redundant_requires.add(req_req_id)

    def _write_templates(self, hostnames):
        node_tasks = {}
        for hostname in hostnames:
            node_tasks[hostname] = self._get_node_tasks_for_hostname(hostname)

        templates = PuppetManagerTemplates(self)
        self._set_task_redundant_requires(node_tasks)

        ms_hostname = self.get_ms_hostname()
        for node in self._get_specific_nodes(hostnames):
            log.trace.debug("updating manifest for %s", node.hostname)
            cluster_type = "NON-CMW"
            cl_type = self.model_manager.get_cluster(node)
            if cl_type is not None:
                clust_prop = cl_type.show_item()
                if clust_prop['item_type'] == "cmw-cluster":
                    cluster_type = "CMW"

            pp_file = self.manifest_file("%s.pp" % (node.hostname).lower())

            if node.hostname in node_tasks:
                tasks = node_tasks[node.hostname]
                task_dict = dict((t.unique_id, t) for t in tasks)
                task_list = task_dict.values()
                task_list.sort(
                    lambda rhs, lhs: cmp(rhs.unique_id, lhs.unique_id)
                )
            elif not self._exists(pp_file):
                task_list = []
            else:
                continue

            self._write_file(pp_file, templates.create_node_pp(
                node, task_list, ms_hostname, cluster_type)
            )
        self.phase_config_version = self.write_new_config_version()

    def write_new_config_version(self):
        cv_file = self._open_file(
                self.manifest_file(self.config_version_file()), 'r+')
        try:
            # Lock the config_version file so other processes can't interfere
            fcntl.flock(cv_file, fcntl.LOCK_EX)
            try:
                try:
                    old_version = int(cv_file.read())
                except ValueError:
                    # File contained legacy timestamp version pre puppetdb or
                    # the file is empty (post fresh litp install)
                    old_version = 0
                # Overwrite contents of file with new version
                cv_file.seek(0)
                cv_file.truncate()
                new_version = old_version + 1
                self._fchmod(
                    cv_file,
                    (stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
                )
                self._fchown(cv_file)
                cv_file.write(str(new_version))
                cv_file.flush()
                os.fsync(cv_file.fileno())
            finally:
                fcntl.flock(cv_file, fcntl.LOCK_UN)
        finally:
            cv_file.close()
        return new_version

    def _check_puppet_status(self, hostnames, status_to_check="not_applying",
                             sleep_time=PUPPET_RUN_WAIT_BETWEEN_RETRIES):
        if status_to_check == "not_applying":
            log.trace.info("Waiting for puppet before writing manifests.")

        hostnames = set(hostnames)
        remaining_hosts = set(hostnames)
        retry_deadline = PuppetManager.PUPPET_LOCK_TIMEOUT + int(time.time())
        while remaining_hosts:
            ret = self.mco_processor.puppetlock_is_running(
                sorted(list(remaining_hosts))
            )
            # If host is unreachable (or any other error) give up on it
            for host in remaining_hosts & hostnames:
                if ret[host]["errors"]:
                    remaining_hosts.remove(host)
                    continue
                if status_to_check == "applying":
                    if ret[host]["data"]["is_running"]:
                        remaining_hosts.remove(host)
                else:
                    if not ret[host]["data"]["is_running"]:
                        remaining_hosts.remove(host)

            if int(time.time()) > retry_deadline:
                lock_files = {}
                for host in remaining_hosts:
                    try:
                        if status_to_check == "applying":
                            if not ret[host]["data"]["is_running"]:
                                lock_files[host] = dict(ret[host])
                                lock_files[host]["errors"] = \
                                    ("Puppet agent lock file not present")
                                msg = "Puppet agent lock files " \
                                      "not present on {hosts}"
                        else:
                            if ret[host]["data"]["is_running"]:
                                lock_files[host] = dict(ret[host])
                                lock_files[host]["errors"] \
                                    = ("Puppet agent lock file present")
                                msg = "Puppet agent lock files " \
                                      "not cleaned up on {hosts}"

                    except KeyError:
                        # host was AWOL during the last mco(1) execution
                        lock_files[host]["errors"] = "Host unreachable"

                raise McoFailed(msg.format(
                        hosts=", ".join('"' + host + '"' for
                            host in sorted(remaining_hosts))
                    ), result=lock_files
                )

            if remaining_hosts:
                self._sleep_if_not_killed(
                            sleep_time,
                            self.killed,
                            self._sleep
                        )

    def _stop_puppet_applying(self, hostnames):
        ret = self.mco_processor.stop_puppet_applying(sorted(list(hostnames)))
        for host in hostnames:
            host_result = ret[host]
            out = host_result.get('data', {}).get('out')
            if host_result["errors"] or \
                    self._is_mco_status_error(host_result):
                log.event.error("Mco action kill_puppet_agent failed"
                                " on host: {0}".format(host))
                if self._is_mco_status_error(host_result) \
                        and not host_result["errors"]:
                    host_result["errors"] = \
                        "MCO action kill_puppet_agent failed"

                raise McoFailed("Mco action kill_puppet_agent failed",
                                result=ret)
            log.trace.info("{0} on host: {1}".format(out, host))

    def _is_mco_status_error(self, host_result):
        status = host_result.get('data', {}).get('status')
        if status:
            return True
        return False

    def _check_mco_agent_status_for_errors(self, hostnames, mco_result,
                                           err_msg):
        for host in hostnames:
            host_result = mco_result[host]

            if self._is_mco_status_error(host_result) \
                    and not host_result["errors"]:
                host_result["errors"] = err_msg
        return mco_result

    def _clear_puppet_cache(self, hostnames):
        result = self.mco_processor.clear_puppet_cache(hostnames)
        return self._check_mco_agent_status_for_errors(hostnames,
                                                       result,
                                                       "MCO action clean in "
                                                       "agent puppetcache "
                                                       "failed.")

    def _is_puppet_alive(self, hostnames):
        puppet_infos = self.mco_processor.status_puppet(hostnames)
        log.trace.debug("puppet status infos: '%s'", puppet_infos)
        for node, puppet_info in puppet_infos.items():
            log.trace.debug("puppet status info: '%s'", puppet_info)
            try:
                if puppet_info['data']['applying'] == True or \
                        puppet_info['data']['idling'] == True:
                    log.trace.debug("puppet still alive on '%s'", node)
                    return True
            except KeyError:
                log.trace.debug('No "applying" or "idling" key in puppet '\
                        'status info')
        log.trace.debug("puppet not applying")
        return False

    def _get_nodes(self):
        return [node for node in self.model_manager.get_all_nodes()
                if not node.is_removed()]

    def _get_specific_nodes(self, hostnames):
        return [node for node in self.model_manager.get_all_nodes()
                if not node.is_removed() and
                (node.hostname in hostnames or node.is_initial())]

    def get_ms_hostname(self):
        return self.model_manager.query("ms")[0].hostname

    def remove_certs(self):
        initial_nodes = self._get_initial_nodes()
        ms_hostname = self.get_ms_hostname()
        self.mco_processor.clean_puppet_certs(initial_nodes, ms_hostname)

    def _get_initial_nodes(self, exclude_ms=False):
        initial_nodes = set()
        for node in self.model_manager.get_all_nodes():
            if exclude_ms and node.is_ms():
                continue
            if node.is_initial():
                initial_nodes.add(node)
        return initial_nodes

    def remove_manifests_clean_tasks(self):
        initial_nodes = self._get_initial_nodes(exclude_ms=True)
        self._prepare_restore_cleanup(initial_nodes)

    def _delete_persisted_tasks_for_node(self, hostname):
        self.data_manager.delete_persisted_tasks_for_node(hostname)

    def purge_node_tasks(self):
        '''
        Function removes all entries for any node in the node_tasks list.
        Also removes any ```hosts::hostentry``` tasks for any node in the
        node_tasks[```MS```] list.
        '''
        restored_nodes = []
        other_nodes = []  # including ms
        for node in self.model_manager.get_all_nodes():
            if not node.is_ms() and node.is_initial():
                restored_nodes.append(node)
            else:
                other_nodes.append(node)

        for node in restored_nodes:
            self._delete_persisted_tasks_for_node(node.hostname)

        restored_hostnames = set([node.hostname for node in restored_nodes])
        for node in other_nodes:
            tasks = []
            for task in self._get_node_tasks_for_hostname(node.hostname):
                if (
                    task.call_type == "hosts::hostentry" and
                    task.kwargs.get("name") in restored_hostnames
                ):
                    continue
                tasks.append(task)
            self._update_persisted_tasks_for_node(node.hostname, tasks)


def format_puppet_report(report):
    """Function formats report received from puppet into form grokkable by
    PuppetManager"""
    formatted_tasks = []

    task_reports = report.split(',')
    # We get a trailing comma in the report
    if not task_reports[-1]:
        task_reports.pop()

    for task_report in task_reports:
        task_id = task_report.split("litp_feedback:task_")[1]

        status = None
        if '=' in task_id:
            status = task_id[task_id.rindex('='):]
            task_id = task_id[:task_id.rindex('=')]
        else:
            continue

        idx = 0
        decoded_id = str()
        while idx < len(task_id):
            char = task_id[idx]
            if ':' == char:
                break
            if '_' == char:
                if '_' == task_id[1 + idx]:
                    decoded_id += '_'
                    idx += 2
                else:
                    try:
                        decoded_id += chr(int(task_id[1 + idx:3 + idx],
                            16))
                    except ValueError:
                        log.trace.info("Could not decode {0} for use in "\
                                "logs".format(task_report))
                    idx += 3
            else:
                decoded_id += char
                idx += 1

        # In order to avoid overloading the logs, we want to cut the kwargs
        # that may have been passed to the ConfigTask we're decoding
        if '_{' in decoded_id:
            kwarg_idx = decoded_id.index('_{')
            decoded_id = decoded_id[:kwarg_idx]

        if status:
            decoded_id += status

        formatted_tasks.append('litp_feedback:task_' + decoded_id)

    return ','.join(formatted_tasks)


class PuppetManager(PuppetManagerNextGen):
    def __init__(self, model_manager, *args, **kwargs):
        super(PuppetManager, self).__init__(model_manager, *args, **kwargs)
        self.data_manager = model_manager.data_manager

    @property
    def node_tasks(self):
        return super(PuppetManager, self).node_tasks

    @node_tasks.setter
    def node_tasks(self, value):  # pylint: disable=arguments-differ
        for hostname, tasks in value.iteritems():
            self._update_persisted_tasks_for_node(hostname, tasks)

    def _update_persisted_tasks_for_node(self, hostname, tasks):
        tasks = list(tasks)
        for task in tasks:
            self.data_manager.session.add(task)
        super(PuppetManager, self)._update_persisted_tasks_for_node(
            hostname, tasks)
