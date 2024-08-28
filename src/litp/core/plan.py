##############################################################################
# COPYRIGHT Ericsson AB 2013
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################


from collections import defaultdict
from itertools import chain
import uuid
import os.path
from time import localtime, strftime
from litp.core.litp_logging import LitpLogger
from litp.core import constants
from litp.core.lazy_property import lazy_property
from litp.core.task import CleanupTask, get_task_node
from litp.core.plan_task import PlanTask
from litp.core.exceptions import PlanStateError
from litp.data.types import Base as DbBase
from litp.data.types import Plan as DbPlan
from litp.plan_types.deployment_plan import deployment_plan_groups
from logging import DEBUG

log = LitpLogger()


class BasePlan(DbPlan, DbBase):
    # pylint: disable=no-member,attribute-defined-outside-init
    def __init__(self, phases, cleanup_tasks=None,
                 lock_tasks=None, plan_type=None):
        '''Creates a plan based on a model and an iterable sequence of tasks.
        :param list phases A list of lists of tasks
        :param list cleanup_tasks An iterable collection of cleanup tasks
        :param dict lock_tasks A dictionary - {node_query_item: (lock_task, \
                                    unlock_task)}
        '''

        self._id = str(uuid.uuid4())
        self._plan_type = plan_type
        self._snapshot_type = ''
        self._state = self.UNINITIALISED

        self._phases = phases

        self._lock_tasks = lock_tasks or {}

        if cleanup_tasks:
            self._phases.append(cleanup_tasks)

        self._init_attributes()

        self._build_phase_dependencies()

    def initialize_from_db(self, data_manager, model_manager):
        if getattr(self, "_initialized", False):
            return

        self._data_manager = data_manager
        self._model_manager = model_manager
        self._init_attributes()
        # in case of null values, we are most probably in a non-phase-reordered
        # to phase-reordered litp upgrade scenario, so build dependencies.
        if self._required_phases is None:
            self._build_phase_dependencies()
        self.set_ready()

    def _init_attributes(self):
        self._find_tasks_cache = None
        self._acting_tasks_cache = defaultdict(set)
        self._task_id_index = {}
        self._initialized = True
        self.current_phase = None

    def set_ready(self):
        '''
        Marks a plan as ready when it has been successfully created.
        '''

        if self.is_uninitialised():
            self._state = self.INITIAL

    @lazy_property
    def _phases(self):  # pylint: disable=method-hidden
        phase_seq_id = -1
        phases = []
        current_phase = None
        for plan_task in self._plan_tasks:
            if plan_task.phase_seq_id != phase_seq_id:
                if current_phase:
                    phases.append(current_phase)
                current_phase = []
                phase_seq_id = plan_task.phase_seq_id
            task = plan_task.task
            task.initialize_from_db(self._data_manager, self._model_manager)
            current_phase.append(task)
        phases.append(current_phase)
        return phases

    @property
    def celery_task_id(self):
        return self._celery_task_id if self._celery_task_id else None

    @celery_task_id.deleter
    def celery_task_id(self):
        self._celery_task_id = ""

    @celery_task_id.setter
    def celery_task_id(self, value):
        self._celery_task_id = value

    def populate_plan_tasks(self):
        for phase_seq_id, phase in enumerate(self._phases):
            for task_seq_id, task in enumerate(phase):
                plan_task = PlanTask(task, phase_seq_id, task_seq_id)
                self._plan_tasks.append(plan_task)

    def _build_acting_tasks_cache(self):
        for task_in_plan in self.get_tasks():
            for task_item in task_in_plan.all_model_items:
                if task_item._model_item is None:
                    continue
                self._acting_tasks_cache[task_item.vpath].add(task_in_plan)

    def _build_phase_dependencies(self):
        """ Builds phase dependencies based upon cluster dependency_list """
        required_phases = {}
        section_ends = {}
        extended_sections = set([])
        phase_cluster_ids = {}

        for phase_idx in xrange(len(self.phases)):
            required_phases[phase_idx] = set([])
            current_phase_cluster_id = self._phase_cluster_id(phase_idx)
            phase_cluster_ids[phase_idx] = current_phase_cluster_id

            if phase_idx == 0:
                section_ends[current_phase_cluster_id] = phase_idx
                continue

            prev_phase_cluster_id = phase_cluster_ids[phase_idx - 1]
            if current_phase_cluster_id == prev_phase_cluster_id:
                # continuation of a cluster or non-parallalisable phase
                required_phases[phase_idx].add(phase_idx - 1)
                section_ends[current_phase_cluster_id] = phase_idx

            elif (self._req_clusters(phase_idx) & set(section_ends.keys())):
                section_ends[current_phase_cluster_id] = phase_idx

                for req_cluster in self._req_clusters(phase_idx):
                    if req_cluster in section_ends.keys():
                        required_phases[phase_idx].add(
                            section_ends[req_cluster]
                        )
                        extended_sections.add(req_cluster)

            elif prev_phase_cluster_id != "" and \
                    current_phase_cluster_id == "":
                # Non-parallelisable phase following a cluster-specific phase
                required_phases[phase_idx].add(phase_idx - 1)
                for cluster_id, last_phase in section_ends.iteritems():
                    if cluster_id not in extended_sections and \
                            cluster_id != "":
                        required_phases[phase_idx].add(last_phase)

                section_ends[current_phase_cluster_id] = phase_idx

            else:
                if current_phase_cluster_id in section_ends.keys():
                    # Continuation of a cluster seen previously in the plan
                    required_phases[phase_idx].add(
                        section_ends[current_phase_cluster_id]
                    )
                    section_ends[current_phase_cluster_id] = phase_idx
                else:
                    # First phase for this cluster
                    section_ends[current_phase_cluster_id] = phase_idx
                    last_non_parallel_phase = section_ends.get("")
                    if last_non_parallel_phase is not None:
                        required_phases[phase_idx].add(last_non_parallel_phase)

        log.trace.debug(
            "BasePlan._build_phase_dependencies():"
            " phase_cluster_ids=%s"
            " required_phases=%s",
            phase_cluster_ids, required_phases)
        # json object keys must be strings, our values should be lists
        first_sort = (self._required_phases is None)
        self._required_phases = dict(
            (unicode(k), list(sorted(v)))
            for k, v in required_phases.iteritems())
        if first_sort and log.log_level() == DEBUG:
            self._dump_phase_graph()

    def _dump_phase_graph(self):
        import pydot
        graph = pydot.Dot()
        start_node = pydot.Node(name="Start")
        graph.add_node(start_node)
        for phase_index in range(len(self.phases)):
            cluster_ids = self._phase_cluster_ids(phase_index)
            node_label = "{%s}" % "|".join(
                    ["Phase%s" % str(phase_index + 1)] + sorted(cluster_ids))
            phase_node = pydot.Node(
                name="Phase%s" % (phase_index,),
                label=node_label,
                shape='Mrecord')
            graph.add_node(phase_node)
        for phase, required_phases in self._required_phases.iteritems():
            begin = "Phase%s" % (phase,)
            if phase == "-1":
                begin = "Start"
            for required_phase in required_phases:
                required_phase_edge = pydot.Edge(
                                        begin,
                                        "Phase%s" % (required_phase,),
                                        color="red",
                                        constraint="false")
                graph.add_edge(required_phase_edge)
        graph_name = strftime(
            "phase_graph_%%Y%%m%%d%%H%%M%%S_%s.dot" % (
                uuid.uuid4()), localtime())
        graph_full_path = os.path.join("/var/log/litp", graph_name)
        graph.write(graph_full_path)

    def _get_task_cluster(self, task):
        """ Get cluster for specified task."""
        task_node = get_task_node(task)
        if task_node:
            return task_node.get_cluster()

        if task.model_item:
            return task.model_item.get_cluster()

    def _get_cluster_phase(self, phase_index):
        """ Get cluster for phase, None if different clusters found."""
        cluster = None
        for task in self.phases[phase_index]:
            # When resuming execution of a failed phase, it is possible to have
            # previously successfully executed tasks whose model item has been
            # deleted from the model
            if isinstance(task.model_item, basestring):
                continue

            if deployment_plan_groups.PRE_CLUSTER_GROUP == task.group:
                break

            task_cluster = self._get_task_cluster(task)
            if (task_cluster is None or
               (cluster is not None and task_cluster != cluster)):
                cluster = None
                break
            cluster = self._get_task_cluster(task)
        return cluster

    def _get_clusters_in_phase(self, phase_index):
        clusters_in_phase = set()
        for task in self.phases[phase_index]:
            if isinstance(task.model_item, basestring):
                continue
            task_cluster = self._get_task_cluster(task)
            if task_cluster not in clusters_in_phase and \
                                 task_cluster is not None:
                clusters_in_phase.add(task_cluster)
        return clusters_in_phase

    def _phase_cluster_ids(self, phase_index):
        clusters_in_phase = self._get_clusters_in_phase(phase_index)
        cluster_ids = set([])
        for c in clusters_in_phase:
            if c is not None:
                cluster_ids.add(c.item_id)
            else:
                cluster_ids.add("")
        return cluster_ids

    def _phase_cluster_id(self, phase_index):
        """ Get cluster ID for given phase """
        phase_cluster_item = self._get_cluster_phase(phase_index)
        if phase_cluster_item is None:
            return ""
        else:
            return phase_cluster_item.item_id

    def _req_clusters(self, phase_index):
        """ Get required cluster ID for given phase """
        clusters = self._get_clusters_in_phase(phase_index)
        required_clusters = set([])
        for cluster in clusters:
            if cluster and hasattr(cluster, 'dependency_list') \
                            and cluster.dependency_list is not None:
                required_clusters.update(
                    set(i for i in cluster.dependency_list.split(",")
                        if i != ""))
        return required_clusters

    def ready_phases(self, completed_phase_idx):
        """
        Returns a set comprising the indices of all phases that are ready to be
        started.
        """
        ready_phases = set([])

        resume_phases = []
        successful_phases = []
        if completed_phase_idx == -1:
            for phase_idx, phase in enumerate(self.phases):
                if any(t.state == constants.TASK_FAILED for t in phase):
                    # We're in a resume scenario
                    for task in phase:
                        if task.state == constants.TASK_FAILED:
                            task.state = constants.TASK_INITIAL

                    resume_phases.append(phase_idx)
                elif all(t.state == constants.TASK_SUCCESS for t in phase):
                    successful_phases.append(phase_idx)

        ready_phases |= set(resume_phases)
        if successful_phases:
            for successful_phase in successful_phases:
                ready_phases |= self.ready_phases(successful_phase)

        if resume_phases:
            self._data_manager.commit()
            return ready_phases

        for phase_idx, phase in enumerate(self.phases):
            if phase_idx <= completed_phase_idx:
                continue

            phase_reqs = self._required_phases.get(unicode(phase_idx), [])
            if completed_phase_idx > -1:
                if not completed_phase_idx in phase_reqs:
                    continue

            if any(t.state == constants.TASK_INITIAL for t in phase):
                if all(self._phase_complete(req) for req in phase_reqs):
                    ready_phases.add(phase_idx)

        return ready_phases

    def _phase_complete(self, phase_index):
        """ Return True if a phase is complete """
        for task in self._phases[phase_index]:
            if task.state != constants.TASK_SUCCESS:
                return False
        return True

    def run(self):
        if self._state not in (self.INITIAL, self.FAILED):
            raise PlanStateError('Plan not in initial state')
        self._build_phase_dependencies()
        self._state = self.RUNNING

    def stop(self):
        if self._state != self.RUNNING:
            raise PlanStateError('Plan not currently running')
        self._state = self.STOPPING

    def end(self):
        if self._state == self.RUNNING:
            if self.all_phases_complete():
                self._state = self.SUCCESSFUL
            else:
                self._state = self.FAILED
        elif self._state == self.STOPPING:
            if self.all_phases_complete():
                self._state = self.SUCCESSFUL
            else:
                self._state = self.STOPPED
        else:
            raise PlanStateError('Plan not active', self._state)

    def mark_invalid(self):
        if self._state not in (self.INITIAL, self.FAILED):
            raise PlanStateError('Plan not in runnable state', self._state)
        self._state = self.INVALID

    def __eq__(self, rhs):
        return (
            rhs and isinstance(rhs, BasePlan) and
            len(self.phases) == len(rhs.phases) and
            all(
                set(phase_tasks) == set(rhs_phase_tasks) for
                phase_tasks, rhs_phase_tasks in zip(self.phases, rhs.phases)
            ) and
            self._state == rhs._state
        )

    def __repr__(self):
        return "<Plan {0}: {1}>".format(self.phases, self._state)

    @property
    def state(self):
        '''Returns the state of the plan as a human-readable string.
        :return Plan state
        :rtype str
        '''
        return self._state

    @property
    def plan_type(self):
        return self._plan_type

    @plan_type.setter
    def plan_type(self, value):
        self._plan_type = value

    @property
    def snapshot_type(self):
        return self._snapshot_type

    @property
    def phase_tree_graph(self):
        return {
            "required_phases": self._required_phases
        }

    @snapshot_type.setter
    def snapshot_type(self, value):
        self._snapshot_type = value

    @property
    def has_cleanup_phase(self):
        return isinstance(self._phases[-1][0], CleanupTask)

    def has_failed(self):
        return self.has_failures() and not self.is_running()

    def is_initial(self):
        return self._state == self.INITIAL

    def is_running(self):
        return self._state == self.RUNNING

    def is_failed(self):
        return self._state == self.FAILED

    def is_stopping(self):
        return self._state == self.STOPPING

    def is_stopped(self):
        return self._state == self.STOPPED

    def is_active(self):
        return self.state in [self.RUNNING, self.STOPPING]

    def is_invalid(self):
        return self.state == self.INVALID

    def is_uninitialised(self):
        return self.state == self.UNINITIALISED

    def is_final(self):
        return self.state in (
            self.SUCCESSFUL,
            self.FAILED,
            self.STOPPED,
            self.INVALID
        )

    def is_cleanup_phase(self, index):
        return self.has_cleanup_phase and index == len(self._phases) - 1

    def has_failures(self):
        for phase in self._phases:
            for task in phase:
                if task.state == constants.TASK_FAILED:
                    return True
        return False

    def all_phases_complete(self):
        for phase in self._phases:
            for task in phase:
                if task.state != constants.TASK_SUCCESS:
                    return False
        return True

    def can_create_plan(self):
        return self._state not in (self.RUNNING, self.STOPPING)

    def get_tasks(self, filter_type=None):
        flatten = chain.from_iterable
        return list(self.filter_tasks(flatten(self.phases), filter_type))

    def find_tasks(self, **properties):
        if self._find_tasks_cache is None:
            self._find_tasks_cache = {}
            self._build_acting_tasks_cache()

        phase = properties.get('phase')
        if phase == 'current':
            phase = self.current_phase
            if phase is None:
                # plan isn't running
                return set()
        elif phase is not None and (phase < 0 or phase >= len(self._phases)):
            return set()

        model_item = properties.get('model_item')
        vpath = None
        if model_item:
            # model items (Query Items) aren't hashable well enough for this
            # purpose
            vpath = model_item.vpath

        tasks = self._find_tasks_cache.get((phase, vpath))
        if not tasks:
            if vpath:
                tasks = self._acting_tasks_cache[vpath]
                if phase is not None:
                    phase_tasks = set(self._phases[phase][:])
                    tasks = tasks & phase_tasks

                self._find_tasks_cache[(phase, vpath)] = tasks
            else:
                if phase is not None:
                    tasks = set(self._phases[phase][:])
                else:
                    try:
                        tasks = self._find_tasks_cache[(phase, None)]
                    except KeyError:
                        tasks = set(self.get_tasks())

                # cache for phase only search. phase can be None meaning all
                # phases
                self._find_tasks_cache[(phase, None)] = tasks

        # never cache searches involving state!
        state = properties.get('state')
        if state:
            if isinstance(state, str):
                state = [state]
            tasks = set(task for task in tasks if task.state in state)

        return tasks

    @property
    def phases(self):
        return self._phases

    @property
    def _tasks(self):
        return self.get_tasks()

    def get_phase(self, index):
        try:
            return self._phases[index]
        except IndexError:
            return None

    def filter_tasks(self, task_iterable, filter_type=None):
        if not filter_type:
            return task_iterable
        else:
            return [task for task in task_iterable if \
                    isinstance(task, filter_type)]

    def _index_tasks_by_phase(self, phase_index):
        if self.get_phase(phase_index):
            phase_tasks = self._task_id_index.get(phase_index, {})
            for task in self.get_phase(phase_index):
                phase_tasks[task.task_id] = task
            self._task_id_index[phase_index] = phase_tasks

    def get_task(self, phase_index, task_id):
        if not self._task_id_index.get(phase_index):
            self._index_tasks_by_phase(phase_index)
        phase_tasks = self._task_id_index.get(phase_index)
        if phase_tasks:
            return phase_tasks.get(task_id)
        return None


class Plan(BasePlan):

    def __init__(self, phases, cleanup_tasks=None, lock_tasks=None,
                 plan_type=constants.DEPLOYMENT_PLAN):
        super(Plan, self).__init__(
            phases=phases,
            cleanup_tasks=cleanup_tasks,
            lock_tasks=lock_tasks,
            plan_type=plan_type
        )


class SnapshotPlan(BasePlan):

    def __init__(self, phases, snapshot_tasks=None,
                 cleanup_tasks=None, lock_tasks=None, plan_type=''):
        '''Creates a plan based on a model and an iterable sequence of tasks.
        :param list phases A list of lists of tasks
        :param list snapshot_tasks An iterable collection of snapshot tasks
        :param list cleanup_tasks An iterable collection of cleanup tasks
        :param dict lock_tasks A dictionary - {node_query_item: (lock_task, \
                                    unlock_task)}
        :param str plan_type A string that describes the snapshot plan type
        '''
        super(SnapshotPlan, self).__init__(
            phases, cleanup_tasks, lock_tasks,
            plan_type=plan_type
        )

        if snapshot_tasks:
            phase_pos = 0
            if self._lock_tasks:
                phase_pos = 1

            self._phases.insert(phase_pos, snapshot_tasks)

        # rebuild phase dependencies linearly
        self._build_phase_dependencies()

    def _build_phase_dependencies(self):
        # TORF-124437: snapshot plans should remain serially executed
        required_phases = {}
        for phase_idx, _ in enumerate(self.phases):
            required_phases[phase_idx] = set([])
            if phase_idx == 0:
                continue
            required_phases[phase_idx].add(phase_idx - 1)

        # json object keys must be strings, our values should be lists
        self._required_phases = dict(
            (unicode(k), list(sorted(v)))
            for k, v in required_phases.iteritems())
