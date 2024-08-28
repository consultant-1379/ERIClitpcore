import logging

from collections import defaultdict, namedtuple
from itertools import chain

from litp.core.topsort import topsort
from litp.core.model_manager import QueryItem
from litp.core.plan import SnapshotPlan
from litp.core.litp_logging import LitpLogger
from litp.core.task import ConfigTask
from litp.core.task import CallbackTask
from litp.core.task import Task
from litp.core.task import (get_task_node,
                            can_have_dependency)
from litp.core.exceptions import ViewError
from litp.core import constants
from litp.core.etlogger import ETLogger, et_logged
from litp.plan_types.remove_snapshot import (
    REMOVE_SNAPSHOT_RULESET,
    REMOVE_SNAPSHOT_TAGS
)
from litp.plan_types.create_snapshot import (
    CREATE_SNAPSHOT_RULESET,
    CREATE_SNAPSHOT_TAGS
)
from litp.plan_types.restore_snapshot import (
    RESTORE_SNAPSHOT_RULESET,
    RESTORE_SNAPSHOT_TAGS
)
from litp.plan_types.deployment_plan import DEPLOYMENT_PLAN_RULESET
from litp.plan_types.deployment_plan.deployment_plan_groups import (
    group_requires_cluster_sorting,
    is_node_group,
    PRE_NODE_CLUSTER_GROUP,
    VXVM_UPGRADE_GROUP,
)
from litp.plan_types.deployment_plan.deployment_plan_tags import (
    VXVM_UPGRADE_TAG
)
from litp.enable_metrics import apply_metrics


log = LitpLogger()
etlog = ETLogger(log.trace.debug, "PlanBuilder ET")
et_logged = et_logged(etlog)


_net_task_item_types = [
    'network-interface',
    'firewall-node-config',
    'firewall-cluster-config',
    'firewall-rule'
]
_package_item_types = ['package']
_repository_item_types = ['yum-repository']
special_config_item_ids = [
    'firewall-cluster-config',
    'firewall-node-config'
]


def log_tasks(tasks):
    if not log.trace.isEnabledFor(logging.DEBUG):
        return
    for task in tasks:
        log.trace.debug("  %s %s", task, task.description)


class TaskCollection(list):
    def __init__(self, iterable=None):
        if iterable is None:
            iterable = []
        super(TaskCollection, self).__init__(iterable)
        self._found_by_vpath = {}
        self._found_by_partial_vpath = {}
        self._found_task_plugin_requires = {}
        self._found_by_call_type_call_id = {}

    def find_tasks(self, **criteria):
        vpath = criteria.get('vpath')
        if vpath:
            found = self._found_by_vpath.get(vpath)
            if found is None:
                found = set(task for task in self
                            if task.item_vpath == vpath)
                self._found_by_vpath[vpath] = found
            return found

        partial_vpath = criteria.get('partial_vpath')
        if partial_vpath:
            found = self._found_by_partial_vpath.get(partial_vpath)
            if found is None:
                found = set(task for task in self
                            if task.item_vpath.startswith(partial_vpath))
                self._found_by_partial_vpath[partial_vpath] = found
            return found

        call_type = criteria.get("call_type")
        call_id = criteria.get("call_id")

        if call_type and call_type:
            call_type_call_id = (call_type, call_id)
            found = self._found_by_call_type_call_id.get(call_type_call_id)
            if found is None:
                found = set(task for task in self
                            if task.call_type == call_type
                            and task.call_id == call_id)
                self._found_by_call_type_call_id[call_type_call_id] = found
            return found

        return []

    def get_plugin_requires(self, task):
        """Retrieves a set of tasks which are dependencies of the current task
        specified by a plugin"""

        task_id = id(task)
        found = self._found_task_plugin_requires.get(task_id)
        if found is None:
            found = set()
            for dependency in task.requires:
                if isinstance(dependency, QueryItem):
                    vpath = dependency.vpath
                    found |= self.find_tasks(partial_vpath=vpath)
                elif isinstance(dependency, Task):
                    # never use previously succesful CallbackTasks
                    # they may linger in a previously successful
                    # ConfigTask.requires
                    if not (isinstance(dependency, CallbackTask)
                            and dependency.state != constants.TASK_INITIAL):
                        # If the dependency is not present in the collection,
                        # don't pull it in
                        if dependency in self:
                            found.add(dependency)
                elif isinstance(dependency, tuple) and len(dependency) == 2:
                    call_type, call_id = dependency
                    found |= self.find_tasks(call_type=call_type,
                                             call_id=call_id)
            found.discard(task)  # don't let it have itself
            self._found_task_plugin_requires[task_id] = found
        return found


@et_logged
def get_cluster_configs_vpaths(model_manager):
    fw_configs_vpaths = []
    norm_configs_vpaths = []
    for cluster in model_manager.query('cluster'):
        # Get vpaths for cluster-level configs for tasks that need to be
        # executed in a different order than the siblings require dictates
        try:
            for cfg in cluster.configs:
                if cfg.item_type_id in special_config_item_ids:
                    fw_configs_vpaths.append(cfg.vpath)
                else:
                    norm_configs_vpaths.append(cfg.vpath)
        except AttributeError:  # no cluster.configs or no cfg.vpath
            pass

        try:
            for node in cluster.nodes:
                for cfg in node.configs:
                    if cfg.item_type_id in special_config_item_ids:
                        fw_configs_vpaths.append(cfg.vpath)
                    else:
                        norm_configs_vpaths.append(cfg.vpath)
        except AttributeError:  # no node.configs or no cfg.vpath
            pass

    return fw_configs_vpaths, norm_configs_vpaths


@et_logged
def get_ms_configs_vpaths(model_manager):
    ms_fw_configs_vpaths = []
    ms_norm_configs_vpaths = []
    mss = model_manager.query('ms')
    try:
        for ms in mss:
            for cfg in ms.configs:
                if cfg.item_type_id in special_config_item_ids:
                    ms_fw_configs_vpaths.append(cfg.vpath)
                else:
                    ms_norm_configs_vpaths.append(cfg.vpath)
    except AttributeError:  # no ms.configs or no cfg.get_vpath
        pass

    return ms_fw_configs_vpaths, ms_norm_configs_vpaths


@et_logged
def _preprocess_tasks_in_task_group(model_manager, tasks, configs_vpaths):
    """Make cluster-level ConfigTasks act as if they were node level for the
    purpose of setting dependencies in nodes"""

    def update_config_task_model_items(tasks, configs_vpaths,
                                       fake_mitem_name='routes'):
        for t in tasks:
            if any(t.item_vpath.startswith(cfg_vpath)
                    for cfg_vpath in configs_vpaths):
                t._special_model_item = t.model_item
                # temporarily substitute model_item on no node tasks with
                # node level model item for the purpose of sorting
                t.model_item = getattr(t.node, fake_mitem_name)

    cfg_tasks = [t for t in tasks if isinstance(t, ConfigTask)]
    # Select ConfigTasks which hang off cluster/config or below

    cluster_configs_vpaths, ms_configs_vpaths = configs_vpaths

    fw_configs_vpaths, norm_configs_vpaths = cluster_configs_vpaths
    update_config_task_model_items(cfg_tasks, fw_configs_vpaths)
    update_config_task_model_items(
        cfg_tasks, norm_configs_vpaths, 'configs')

    ms_fw_configs_vpaths, ms_norm_configs_vpaths = ms_configs_vpaths
    update_config_task_model_items(cfg_tasks, ms_fw_configs_vpaths)
    update_config_task_model_items(
        cfg_tasks, ms_fw_configs_vpaths, 'configs')

    return tasks


def _associated_items_determinable(tasks):
    return all(task.all_model_items_determinable() for task in tasks)


def merge_prev_successful_and_current_tasks(previous, current):
    """Merge previously successful tasks and new tasks."""

    if not previous:
        # no need to merge anything
        return current

    current_uids = dict((task.unique_id, i)
                              for i, task in enumerate(current))
    tasks = []
    for task in previous:
        # if previous task not in current set include it
        if task.unique_id not in current_uids:
            tasks.append(task)
        # if previous task in current set use the old task, remove the new one
        elif task == current[current_uids[task.unique_id]] and \
                task.group == current[current_uids[task.unique_id]].group:
            tasks.append(task)
            log.trace.debug(
                "PlanBuilder previously successful task reused: %s",
                task)
            # reset task to Initial if all associated items not determinable
            if not _associated_items_determinable((task,)):
                task.state = constants.TASK_INITIAL
            # remove new task (keep index, as it must stay intact)
            current[current_uids[task.unique_id]] = None
    tasks += [curr for curr in current if curr]
    return tasks


class BasePlanBuilder(object):
    '''
    This is a base class that provides generic facilities to specialised plan
    builders
    '''

    def __init__(self, model_manager, tasks, lock_tasks=None):
        self._model_manager = model_manager
        self.tasks = tasks
        self.previously_successful_tasks = []
        self.lock_tasks = lock_tasks or {}
        self.phases = []
        self._model_dependency_graph = None
        self._configs_vpaths = None
        apply_metrics(self)

    @et_logged
    def _sort_tasks_within_phases(self, phases, graph):
        """Method sorts tasks within phase so that CallbackTasks are always
        before ConfigTasks, CallbackTasks are in order they were fed into
        PlanBuilder.
        ConfigTasks are sorted based on dependencies between
        them: tasks that are required come before tasks that require them or if
        no dependencies then by their model items' vpaths"""
        def dependency_compare(x, y):
            if isinstance(x, CallbackTask):
                if isinstance(y, CallbackTask):
                    return x._index_in_tasks - y._index_in_tasks
                return -1
            elif isinstance(y, CallbackTask):
                return 1

            if y in graph[x]:
                return 1
            elif x in graph[y]:
                return -1
            return cmp(x.model_item.vpath, y.model_item.vpath)

        for phase in phases:
            phase.sort(cmp=dependency_compare)
        return phases

    @et_logged
    def _get_dependency_graph(self, tasks):
        require_graph = self._create_graph_from_task_requires(tasks)
        tasks = _preprocess_tasks_in_task_group(
            self._model_manager, tasks, self._configs_vpaths)
        combined_graph = self._create_graph_from_static_sibling_require(
            tasks, require_graph)
        # revert special model item
        for task in tasks:
            if hasattr(task, '_special_model_item'):
                task.model_item = task._special_model_item

        combined_graph = bridge_static_and_plugin_dependencies(
            combined_graph
        )
        self._copy_cfg_tasks_depinfo_for_puppet_use(combined_graph)
        return combined_graph

    @et_logged
    def _copy_cfg_tasks_depinfo_for_puppet_use(self, graph):
        for task, deps in graph.items():
            if isinstance(task, ConfigTask):
                task._requires = set(dep.unique_id for dep in deps
                                      if isinstance(dep, ConfigTask))
        return graph

    @et_logged
    def _sort_tasks(self, tasks):
        '''Builds a list of phases, each comprising a non-empty list of tasks
        based on model sibling dependencies and requires dependencies in tasks
        :return List of phases
        :rtype list
        '''
        graph = self._get_dependency_graph(tasks)
        phases = BasePlanBuilder._topsort(graph)
        phases = BasePlanBuilder._compact_phases(phases, graph)
        phases = BasePlanBuilder._segregate_callback_tasks(phases, graph)
        phases = self._remove_prev_successful_tasks(phases)
        phases = self._sort_tasks_within_phases(phases, graph)
        return phases

    @staticmethod
    @et_logged
    def _topsort(graph):
        phases = topsort(graph)
        return phases

    @et_logged
    def _remove_prev_successful_tasks(self, phases):
        """Remove tasks that have been successfully executed in the past"""

        ignored_tasks = defaultdict(list)
        for task in self.previously_successful_tasks:
            ignored_tasks[task.call_type].append(task)

        new_phases = []
        for phase in phases:
            new_phase = []
            for task in phase:
                if _associated_items_determinable((task,)):
                    if task.state != constants.TASK_INITIAL:
                        continue
                    if isinstance(task, ConfigTask):
                        if task.call_type in ignored_tasks:
                            if task in ignored_tasks[task.call_type]:
                                continue
                else:
                    if task in self.previously_successful_tasks:
                        if task.state == constants.TASK_SUCCESS:
                            continue
                new_phase.append(task)

            if new_phase:
                new_phases.append(new_phase)
        return new_phases

    @staticmethod
    @et_logged
    def _compact_phases(phases, graph):
        """Reduce numer of phases"""
        new_phases = []
        for phase in phases:
            # tasks in same phase at this point are guaranteed (topsort) to not
            # have model/plugin dependencies between themselves
            net_tasks = []
            callback_tasks = []
            other_tasks = []
            for task in phase:
                if task._net_task:
                    net_tasks.append(task)
                elif isinstance(task, CallbackTask):
                    callback_tasks.append(task)
                else:
                    other_tasks.append(task)

            for task in net_tasks:
                dependencies = graph[task]
                PlanBuilder._place_net_task(new_phases, task, dependencies)

            for task in callback_tasks:
                dependencies = graph[task]
                PlanBuilder._place_regular_task(new_phases, task, dependencies)

            for task in other_tasks:
                dependencies = graph[task]
                PlanBuilder._place_regular_task(new_phases, task, dependencies)
        return new_phases

    @staticmethod
    def get_phase_dependencies(phase, graph):
        phase_deps = set()
        for task in phase:
            phase_deps |= graph[task]
        return phase_deps

    @staticmethod
    def common_tasks(tasks_set_a, tasks_set_b):
        return tasks_set_a & tasks_set_b

    @staticmethod
    def any_net_tasks(tasks):
        return any(task._net_task for task in tasks)

    @staticmethod
    def is_all_config_tasks(tasks):
        return all(isinstance(task, ConfigTask) for task in tasks)

    @staticmethod
    def update_phases_with_segregated_config_tasks(
             phase_index, phases, segregated_config_tasks, graph):
        try:
            next_phase = phases[phase_index + 1]
            next_phase_deps = BasePlanBuilder.get_phase_dependencies(
                                                    next_phase, graph)

            common_deps = BasePlanBuilder.common_tasks(
                    next_phase_deps, set(segregated_config_tasks))

            seg_cfg_net_count = BasePlanBuilder.any_net_tasks(
                                         segregated_config_tasks)
            next_phase_net_count = BasePlanBuilder.any_net_tasks(next_phase)

            next_phase_is_all_cfg = BasePlanBuilder.is_all_config_tasks(
                                                                  next_phase)

            if next_phase_is_all_cfg and not common_deps and \
                    seg_cfg_net_count == next_phase_net_count:
                # Reuse the next phase
                next_phase.extend(segregated_config_tasks)
            else:
                # Inject a new phase for the segregated ConfigTasks
                phases.insert(
                    phase_index + 1,
                    segregated_config_tasks
                )
        except IndexError:
            phases.append(segregated_config_tasks)

    @staticmethod
    @et_logged
    def _segregate_callback_tasks(phases, graph):
        for phase_index, phase in enumerate(phases):
            if BasePlanBuilder._is_mixed_phase(phase):
                segregated_callback_tasks = []
                segregated_config_tasks = []
                for phase_task in phase:
                    if isinstance(phase_task, CallbackTask):
                        segregated_callback_tasks.append(phase_task)
                    else:
                        segregated_config_tasks.append(phase_task)
                # Add segregated callback tasks to the current phase
                phases[phase_index] = segregated_callback_tasks
                BasePlanBuilder.update_phases_with_segregated_config_tasks(
                        phase_index, phases, segregated_config_tasks, graph)
        return phases

    @staticmethod
    def _is_mixed_phase(phase):
        return any(isinstance(task, ConfigTask) for task in phase) and \
            any(isinstance(task, CallbackTask) for task in phase)

    @et_logged
    def _create_graph_from_static_sibling_require(self, tasks, graph):
        vpaths = set(task.item_vpath for task in tasks)
        self._model_dependency_graph = self._model_manager.get_dependencies(
            vpaths)
        return BasePlanBuilder.create_graph_from_static_sibling_require(
            tasks, self._model_dependency_graph, graph)

    @staticmethod
    @et_logged
    def _create_graph_from_task_requires(tasks):
        """
        Creates a task dependency graph by visiting each task and inspecting
        its direct and indirect plugin-defined (as opposed to model-defined)
        dependencies.
        """

        graph = {}
        if not tasks:
            return graph
        log.trace.debug(
            "[Dependency graph] Task require, group '%s', tasks: %s",
            tasks[0].group, len(tasks)
        )
        pass_counter = 0
        for task in tasks:
            graph[task] = set()
            # collect direct and indirect dependencies
            # visits every task and every dependency in task.requires set
            direct_dependencies = tasks.get_plugin_requires(task)
            indirect_deps = set()

            while direct_dependencies:
                queue = []
                for dependency in direct_dependencies:
                    if can_have_dependency(task, dependency):
                        graph[task].add(dependency)
                    for indirect in tasks.get_plugin_requires(dependency):
                        pass_counter += 1

                        # We need indirect_deps to keep track of
                        # already visited indirect dependencies of task.
                        # 'queue' is not suitable for this purpose as it is
                        # reset for every direct dependency.
                        if indirect is task or indirect in indirect_deps:
                            # Cyclic dependency case: A -> B -> A.
                            # Don't include task in its own requires as it will
                            # make the while loop endless.
                            continue
                        queue.append(indirect)
                        indirect_deps.add(indirect)
                direct_dependencies = queue  # accumulate
        log.trace.debug(
            ("[Dependency graph] Task require, group '%s', graph building,"
                "passes: %s"),
            tasks[0].group, pass_counter)
        return graph

    @staticmethod
    def _mark_net_tasks(task):
        # TODO This static method performs business logic and therefore belongs
        # in PlanBuilder instead of BasePlanBuilder
        mitem = task.model_item._model_item
        if any(mitem.is_instance(it) for it in _net_task_item_types)\
                and not task.is_deconfigure():
            task._net_task = True
            log.trace.debug("Mark as '_net_task': %s", task)
        else:
            task._net_task = False

    @staticmethod
    def create_graph_from_static_sibling_require(tasks, model_dependency_graph,
                                                 graph=None):
        """
        Creates a task dependency graph by visiting each task and inspecting
        the direct and indirect model-defined (as opposed to plugin-defined)
        dependencies of its model item.

        If graph arg is present it is updated instead of creating a new one.

        :param tasks: TaskCollection instance.
        :type  tasks: TaskCollection
        :param model_dependency_graph: Graph of task dependencies just
                                        from the model.
        :type  model_dependency_graph: dict
        :param graph: Graph of task dependencies gathered so far, requires
                        the dependencies from task.requires
        :type  graph: dict

        """

        md_graph = model_dependency_graph
        graph = graph or {}
        if not tasks:
            return graph

        log.trace.debug(
            "[Dependency graph] Model require, group '%s', tasks: %s",
            tasks[0].group, len(tasks)
        )

        # helper function
        def _find_tasks_by_vpaths(vpaths):
            found = []
            for vpath in vpaths:
                found.extend(tasks.find_tasks(vpath=vpath))
            return found

        vpaths = {}
        pass_counter = 0
        # create direct dependencies between vpaths from indirect ones
        for vpath, dependencies in md_graph.iteritems():
            vpaths[vpath] = set()
            while dependencies:
                queue = set()
                for dependency in dependencies:
                    pass_counter += 1
                    if dependency in vpaths[vpath]:
                        continue
                    vpaths[vpath].add(dependency)
                    queue |= md_graph.get(dependency, set())
                dependencies = queue
        log.trace.debug(
            "[Dependency graph] Model require, group '%s', "
                "vpath indirect to direct; passes: %s",
            tasks[0].group, pass_counter
        )

        # calculate reversed vpath dependencies
        reversed_vpaths = defaultdict(set)
        for vpath, dependencies in vpaths.items():
            for dep in dependencies:
                reversed_vpaths[dep].add(vpath)
        # For each task, find its model dependencies and add to graph
        pass_counter = 0
        for task in tasks:
            if task not in graph:
                graph[task] = set()
            # if deconfigure use reversed model dependencies
            if task.is_deconfigure():
                dependency_vpaths = reversed_vpaths[task.item_vpath]
            else:
                dependency_vpaths = vpaths.get(task.item_vpath, [])

            dependencies = _find_tasks_by_vpaths(dependency_vpaths)

            for dependency in dependencies:
                # LITPCDS-12114: We do not want to add model dependencies
                # between package tasks
                if all(
                        isinstance(t, ConfigTask) and 'package' == t.call_type
                        for t in (task, dependency)
                    ):
                    continue

                if can_have_dependency(task, dependency) \
                    and dependency not in graph.get(task) \
                        and task not in graph.get(dependency, set()):
                    graph[task].add(dependency)
                pass_counter += 1

        log.trace.debug(
            "[Dependency graph] Model require, group '%s', graph building, "
                "passes: %s",
            tasks[0].group, pass_counter
        )
        return graph


def topsort_deployment_plan_groups():
    """
    Sorts topologically the task groups used in the deployment ruleset based on
    the dependencies defined between them.
    """
    graph = dict((item['group_name'], set(item.get('requires', [])))\
            for item in DEPLOYMENT_PLAN_RULESET)
    return topsort(graph)


def index_groups_by_priority():
    group_priority_index = {}
    for priority_index, groups in enumerate(topsort_deployment_plan_groups()):
        for group in groups:
            group_priority_index[group] = priority_index
    return group_priority_index

GROUP_PRIORITY_INDEX = index_groups_by_priority()


class PlanBuilder(BasePlanBuilder):

    all_groups_sequence = list(chain.from_iterable(
        topsort_deployment_plan_groups()
    ))

    CLUSTER_GROUP_SEQUENCE = [
        group for group in all_groups_sequence if \
            group_requires_cluster_sorting(group)
    ]

    # This is a placeholder name for the task groups that need to be sorted on
    # a per-cluster basis
    PER_CLUSTER_GROUPS = 'cluster_phases'
    try:
        first_cluster_group_idx = all_groups_sequence.index(
            CLUSTER_GROUP_SEQUENCE[0]
        )
        PLAN_GROUP_SEQUENCE = all_groups_sequence[:first_cluster_group_idx] + \
            [PER_CLUSTER_GROUPS]

        try:
            post_cluster_idx = first_cluster_group_idx + \
                len(CLUSTER_GROUP_SEQUENCE)
            PLAN_GROUP_SEQUENCE += all_groups_sequence[post_cluster_idx:]
        except IndexError:
            pass

    except IndexError:
        PLAN_GROUP_SEQUENCE = all_groups_sequence

    def __init__(self, model_manager, tasks, lock_tasks=None):
        super(PlanBuilder, self).__init__(
            model_manager, tasks, lock_tasks
        )
        self.sortable_tasks = None

    def build(self):
        self.phases = []
        tasks_as_set = set(self.tasks)
        successful_as_set = set(self.previously_successful_tasks)

        # shortcut circuit
        if not len(tasks_as_set - successful_as_set) and \
                _associated_items_determinable(tasks_as_set) and \
                not self._model_manager._node_left_locked():
            return self.phases
        PlanBuilder._update_tasks(
            self.previously_successful_tasks + self.tasks)
        sortable_tasks = merge_prev_successful_and_current_tasks(
            self.previously_successful_tasks, self.tasks)
        log.trace.debug("PlanBuilder tasks begin")
        log_tasks(sortable_tasks)
        log.trace.debug("PlanBuilder tasks end")
        self.sortable_tasks = sortable_tasks

        # TODO check if it's necessary
        for index, task in enumerate(sortable_tasks):
            task._index_in_tasks = index

        if sortable_tasks:
            self._configs_vpaths = (
                get_cluster_configs_vpaths(self._model_manager),
                get_ms_configs_vpaths(self._model_manager))
            for plan_group in PlanBuilder.PLAN_GROUP_SEQUENCE:
                if plan_group == PlanBuilder.PER_CLUSTER_GROUPS:
                    group_phases = []

                    # Append phases for each cluster
                    for cluster_phase_tuple in self._get_cluster_phases():
                        for phase_set in cluster_phase_tuple:
                            if len(phase_set) > 0:
                                group_phases.extend(phase_set)

                else:
                    group_tasks = self._get_task_collection_for_group(
                        plan_group
                    ) or []
                    group_phases = self._sort_tasks(group_tasks)

                self.phases.extend(group_phases)

        log.trace.debug("PlanBuilder plan begin")
        for pindex, phase in enumerate(self.phases):
            log.trace.debug("Phase %s", pindex + 1)
            log_tasks(phase)
        log.trace.debug("PlanBuilder plan end")

        return self.phases

    def _lock_tasks_required(self, phases, node_qi):
        return all((
            node_qi.vpath in self.lock_tasks,
            len(phases) > 0
        ))

    def _get_task_collection_for_group(self, group_tag, nodes_vpath=None):
        '''
        Iterates on on the set of effective tasks and returns a TaskCollection
        object of tasks matching a certain tag and node
        '''
        if isinstance(group_tag, str):
            group_tag = [group_tag]
        if nodes_vpath is not None:
            task_collection = TaskCollection()
            for node_vpath in nodes_vpath:
                task_collection.extend(
                     x for x in self.sortable_tasks
                     if x.group in group_tag and
                     get_task_node(x).vpath == node_vpath
                )
        else:
            task_collection = TaskCollection(
                x for x in self.sortable_tasks if x.group in group_tag
            )
        return task_collection

    def _get_task_collection_for_cluster(self, group_tag, cluster_vpath):
        task_collection = TaskCollection()
        if cluster_vpath is not None:
            task_collection.extend(
                 x for x in self.sortable_tasks
                 if group_tag == x.group and
                    x.model_item.get_cluster() and
                    x.model_item.get_cluster().vpath == cluster_vpath
            )
            log.trace.debug("Cluster tasks for %s: %s",
                cluster_vpath, task_collection)
        return task_collection

    @staticmethod
    def _validate_node_upgrade_ordering(values, cluster):
        if not isinstance(values, list):
            raise ViewError('"node_upgrade_ordering" must return a list.'
                    ' {0} returned'.format(type(values)))

        # Check if values is a list of strings
        for value in values:
            if not isinstance(value, basestring):
                raise ViewError('"node_upgrade_ordering" must be a list of '
                '"basestring". {0} found in the list'.format(type(value)))

        # Check if each string is a valid node in the cluster
        cluster_node_ids = [n.item_id for n in cluster.nodes]
        for value in values:
            if value not in cluster_node_ids:
                raise ViewError(
                    '"node_upgrade_ordering" contains a node id that is '
                    'not present in the cluster: {0}'.format(value))

        # Check if each value is unique
        if len(values) > len(set(values)):
            duplicated = set(v for v in values if values.count(v) > 1)
            raise ViewError('"node_upgrade_ordering" contains '
                    'duplicated node ids: {0}'.format(' '.join(duplicated)))

        # Check if no node is missing
        missing_node_ids = set(cluster_node_ids) - set(values)
        if missing_node_ids:
            raise ViewError(
                '"node_upgrade_ordering" does not contain all the nodes within'
                ' the cluster. Missing node ids: {0}'.format(
                    ' '.join(missing_node_ids)))

    def _get_node_ids(self, cluster):
        node_ids = []
        try:
            values = getattr(QueryItem(self._model_manager, cluster),
                    'node_upgrade_ordering')
            if values:
                self._validate_node_upgrade_ordering(values, cluster)
                node_ids.extend(values)
        except AttributeError:
            pass
        if not node_ids:
            node_ids.extend(n.item_id for n in cluster.nodes)
        return node_ids

    def _get_nodes(self, cluster):
        nodes = []
        for node_item_id in self._get_node_ids(cluster):
            nodes.append(
                    self._model_manager.query_model_item(
                        cluster, 'node', item_id=node_item_id)[0])
        return nodes

    def _get_ordered_clusters(self):
        deployments = self._model_manager.query('deployment')
        deployments.sort(key=lambda d: d.item_id)

        ordered_clusters_qi = []
        for deployment in deployments:
            cluster_qi = getattr(QueryItem(self._model_manager, deployment),
                                "ordered_clusters")
            ordered_clusters_qi.extend(cluster_qi)
        ordered_clusters = [qi._model_item for qi in ordered_clusters_qi]
        return ordered_clusters

    def _get_cluster_phases(self):
        '''
        Iterates on clusters and for each yields a namedtuple of the phases in
        the cluster's task groups, in the order in which they are to be
        appended to the plan.
        '''

        # This is a placeholder name for the task groups that need to be run on
        # a locked node
        LOCKED_NODE_PHASES = 'node_lock_phases'

        node_left_locked = self._model_manager._node_left_locked()
        if node_left_locked:
            locked_node_cluster = self._model_manager.get_cluster(
                node_left_locked
            )

        for cluster in self._get_ordered_clusters():
            cluster_group_phases = defaultdict(list)

            sequence = list(PlanBuilder.CLUSTER_GROUP_SEQUENCE)
            # Isolate groups that require node-locking
            if self._cluster_has_lock_tasks(cluster):
                node_sequence = [
                    group for group in sequence if is_node_group(group)
                ]
                # is the node group(s) part of the locked section?
                first_node_group_idx = sequence.index(node_sequence[0])
                sequence = sequence[:first_node_group_idx] + \
                    [LOCKED_NODE_PHASES] + \
                    sequence[first_node_group_idx + len(node_sequence):]

            ClusterPhaseTuple = namedtuple(
                'ClusterPhases',
                ','.join(sequence)
            )

            for group in sequence:
                if group == LOCKED_NODE_PHASES:
                    locked_node_phases = []
                    unlocked_node_phases = []

                    for node in self._get_nodes(cluster):
                        node_vpath = node.vpath
                        node_phases = []

                        for node_group in node_sequence:
                            group_tasks = self._get_task_collection_for_group(
                                node_group, [node_vpath]
                            )
                            group_phases = self._sort_tasks(group_tasks)
                            node_phases += group_phases

                        if self._lock_tasks_required(node_phases, node):
                            locked_node_phases += self._apply_lock_tasks(
                                node_phases, node_vpath
                            )
                        else:
                            unlocked_node_phases += node_phases

                    cluster_group_phases[group] += locked_node_phases + \
                            unlocked_node_phases

                else:
                    if is_node_group(group):
                        group_tasks = self._get_task_collection_for_group(
                            group,
                            [node.vpath for node in
                                self._model_manager.query_model_item(
                                    cluster, 'node')]
                        )
                    else:
                        group_tasks = self._get_task_collection_for_cluster(
                            group,
                            cluster.vpath
                        )
                    cluster_group_phases[group] += self._sort_tasks(
                        group_tasks
                    )

            if node_left_locked and cluster.vpath == locked_node_cluster.vpath:
                if self.lock_tasks:
                    unlock_task = \
                        self.lock_tasks[node_left_locked.vpath][1].copy()
                    cluster_group_phases[PRE_NODE_CLUSTER_GROUP] += [
                        [unlock_task]
                    ]

            yield ClusterPhaseTuple(**cluster_group_phases)

    def _cluster_has_lock_tasks(self, cluster_qi):
        for node_vpath in self.lock_tasks:
            if node_vpath.startswith(cluster_qi.vpath):
                node_qi = self._model_manager.query_by_vpath(node_vpath)
                if node_qi:
                    return True
        return False

    @et_logged
    def _apply_lock_tasks(self, locked_node_phases, node_vpath=None):
        '''
        Bracket a set of node-specific task phases between a lock and unlock
        task, each in their own phase
        '''
        new_phases = []

        node_lock_tasks = self.lock_tasks[node_vpath]
        new_phases = []
        new_phases.append([node_lock_tasks[0]])
        new_phases.extend(locked_node_phases)
        new_phases.append([node_lock_tasks[1]])

        return new_phases

    @staticmethod
    def _update_tasks(tasks):
        '''
        Iterates on a collection of tasks and applies arbitrary processing
        logic to each task.
        '''

        for task in tasks:
            PlanBuilder._update_package_tasks(task)
            PlanBuilder._mark_net_tasks(task)
        # TORF-323439: if only the bond arp_ip_target property was updated
        # and the plan contains a VXVM upgrade, place bond tasks in the
        # same group as the VXVM upgrade tasks
        PlanBuilder._ensure_presence_of_both_vxvm_upgrade_and_bond(tasks)
        return tasks

    @staticmethod
    def _ensure_presence_of_both_vxvm_upgrade_and_bond(tasks):
        '''
        Changes the task group to VXVM_UPGRADE_GROUP if the task is a marked
        bond update and the plan contains tasks on the same nodes which
        are tagged with VXVM_UPGRADE_TAG
        '''

        vxvm_upgrade = False
        affected_nodes = set()
        for task in tasks:
            if hasattr(task, 'tag_name') and \
            task.tag_name == VXVM_UPGRADE_TAG:
                vxvm_upgrade = True
                # These are all CallbackTask so we have to look at model_item
                affected_nodes.add(task.model_item.get_node().hostname)

        for task in tasks:
            if hasattr(task, '_pre_vxvm_bond'):
                if vxvm_upgrade and (task._pre_vxvm_bond == True) and \
                (task.node.hostname in affected_nodes):
                    task.group = VXVM_UPGRADE_GROUP
                del task._pre_vxvm_bond

    @staticmethod
    def _update_package_tasks(task):
        ''' Make sure package tasks go after repository tasks. '''
        mitem = task.model_item._model_item

        if any(mitem.is_instance(it) for it in _package_item_types):
            node = task.model_item.get_node() or task.model_item.get_ms()
            if node and not task.is_deconfigure():
                repo_query_items = set()
                for repo_item_type in _repository_item_types:
                    repo_query_items.update(node.query(repo_item_type,
                                                       is_for_removal=False))
                if repo_query_items:
                    log.trace.debug(
                        'Task %s requires %s',
                        task, repo_query_items
                    )
                    task.requires.update(repo_query_items)

    @staticmethod
    def _place_regular_task(phases, task, dependencies):
        """
        Function places a non-net task as close to the 1st phase as
        possible
        """
        if not phases:
            phases.append([task])
        else:
            for index, phase in reversed(list(enumerate(phases))):
                if any(t._net_task for t in phase):
                    # regular task can't be in a single phase with net tasks
                    if phase is phases[-1]:
                        phases.append([task])
                    else:
                        phases[index + 1].append(task)
                    break

                deps_in_phase = _deps_in_phase(phase, dependencies)
                if deps_in_phase and (isinstance(task, CallbackTask) or
                                      any(isinstance(d, CallbackTask)
                                           for d in deps_in_phase)):
                    # any 2 tasks that have dependency relationship and at
                    # least one of them is a CallbackTask must be kept in
                    # separate phases
                    if phase is phases[-1]:
                        phases.append([task])
                    else:
                        phases[index + 1].append(task)
                    break

                elif phase is phases[0]:
                    phases[0].append(task)
                    break

    @staticmethod
    def _place_net_task(phases, task, dependencies):
        """Function places a net task as close to the 1st phase as possible"""
        # Net tasks should never share a phase with any other tasks
        # and should be put as early as possible to account for dependencies on
        # networking specified inside puppet modules

        # filter out net deps on disk tasks
        for dep in list(dependencies):
            if dep.model_item._model_item.is_instance("disk-base"):
                dependencies.remove(dep)

        if not phases:
            phases.append([task])
        elif not dependencies:
            if all(t._net_task for t in phases[0]):
                phases[0].append(task)
            else:
                phases.insert(0, [task])
        else:
            for index, phase in reversed(list(enumerate(phases))):
                deps_in_phase = _deps_in_phase(phase, dependencies)
                if deps_in_phase:
                    if (isinstance(task, CallbackTask) or
                            any(
                                isinstance(d, CallbackTask) or not d._net_task
                                for d in deps_in_phase
                            )):
                        if phase is phases[-1]:
                            phases.append([task])
                        elif any(t._net_task for t in phases[index + 1]):
                            # append to net phase processed in previous loop
                            phases[index + 1].append(task)
                        else:
                            new_phase = [task]
                            phases.insert(index + 1, new_phase)
                    else:
                        phases[0].append(task)
                    break


@et_logged
def bridge_static_and_plugin_dependencies(graph):
    """Function traverses graph and fills in the gaps in dependencies
    Eg given model-define dependency A -> B
    and plugin-defined task-to-task dependency B -> C
    a task-to-task dependency A -> C should be created if missing"""
    tasks = graph.keys()
    if not tasks:
        return graph
    pass_counter = 0
    for task in tasks:
        dependencies = list(graph[task])  # dependency accumulator
        while dependencies:
            queue = []
            for dependency in dependencies:
                for indirect in graph.get(dependency, []):
                    pass_counter += 1
                    if indirect in graph[task]:
                        continue  # already handled
                    queue.append(indirect)
                    graph[task].add(indirect)
            dependencies = queue  # needed for the while loop to finish
    log.trace.debug("[Dependency graph] Merge model and task dependencies, "
                    "group '%s', passes: %s", graph.keys()[0].group,
                    pass_counter)
    return graph


def _deps_in_phase(phase, dependencies):
    if not dependencies:
        deps_in_phase = set()
    else:
        phase_set = set(phase)
        dependencies_set = set(dependencies)
        deps_in_phase = phase_set & dependencies_set
    return deps_in_phase


def _log_dependencies(graph):
    if not log.trace.isEnabledFor(logging.DEBUG):
        return
    for node, deps in graph.iteritems():
        log.trace.debug("task: %s", node)
        if deps:
            log.trace.debug("deps:")
        for dep in deps:
            log.trace.debug("     %s", dep)


class SnapshotPlanBuilder(object):

    _ruleset = None
    _valid_tags = None
    _unmatched_group_name = None

    def __init__(self, model_manager, plan_type, tasks):
        self.plan_type = plan_type
        self.tasks = tasks
        self.model_manager = model_manager

    @property
    def ruleset(self):
        if self._ruleset is None:
            plan_type_ruleset_map = {
                constants.CREATE_SNAPSHOT_PLAN: CREATE_SNAPSHOT_RULESET,
                constants.REMOVE_SNAPSHOT_PLAN: REMOVE_SNAPSHOT_RULESET,
                constants.RESTORE_SNAPSHOT_PLAN: RESTORE_SNAPSHOT_RULESET,
            }
            self._ruleset = plan_type_ruleset_map.get(self.plan_type.lower())
        return self._ruleset

    @property
    def valid_tags(self):
        if self._valid_tags is None:
            plan_type_tag_map = {
                constants.CREATE_SNAPSHOT_PLAN: CREATE_SNAPSHOT_TAGS,
                constants.REMOVE_SNAPSHOT_PLAN: REMOVE_SNAPSHOT_TAGS,
                constants.RESTORE_SNAPSHOT_PLAN: RESTORE_SNAPSHOT_TAGS,
            }
            self._valid_tags = plan_type_tag_map.get(
                self.plan_type.lower(), []
            )
        return self._valid_tags

    @property
    def unmatched_group_name(self):
        if self._unmatched_group_name is None:
            for rule in self.ruleset:
                if rule.get('unmatched_tasks', False):
                    self._unmatched_group_name = rule['group_name']
                    break
        return self._unmatched_group_name

    def _is_valid_tag(self, tag_name):
        return tag_name in self.valid_tags

    def _build_groups_dependency_graph(self):
        return dict((item['group_name'],
                     set(item.get('requires', []))) for item in self.ruleset)

    def _topsort_groups(self):
        sorted_groups = []
        graph = self._build_groups_dependency_graph()
        for item_list in topsort(graph):
            sorted_groups.extend(item_list)
        return sorted_groups

    def _group_tasks(self):
        group_list = self._topsort_groups()
        groups = dict((group, []) for group in group_list)
        for task in self.tasks:
            task_group = self._extract_ruleset_group_from_task(task)
            groups[task_group].append(task)
        sorted_groups = [(group, groups[group]) for group in group_list]
        log.trace.debug(sorted_groups)
        return sorted_groups

    def _extract_ruleset_group_from_task(self, task):
        for rule in self.ruleset:
            if self._task_matches_criteria(task, rule.get('criteria', {})):
                return rule['group_name']

        return self.unmatched_group_name

    def _task_matches_criteria(self, task, criteria):
        matched = False
        log.trace.debug(
            'Begin task %r match against criteria: %s', task, criteria
        )

        if task.tag_name is not None and not self._is_valid_tag(task.tag_name):
            log.trace.warning(
                'Invalid tag name: <<%s>>. Task %r will be marked as'
                ' untagged', task.tag_name, task
            )
        else:
            for key, value in criteria.iteritems():
                if key == 'task_type':
                    attr_value = task.__class__.__name__
                else:
                    attrs_chain = key.split('.')
                    attr_value = getattr(task, attrs_chain[0], None)
                    for attr_name in attrs_chain[1:]:
                        attr_value = getattr(attr_value, attr_name, None)

                if attr_value != value:
                    matched = False
                    break
                matched = True
        return matched

    def build(self):
        phases = [
            task_list for _, task_list in self._group_tasks() if task_list
        ]
        return SnapshotPlan(
            phases=phases
        )
