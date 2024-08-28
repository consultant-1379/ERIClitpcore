import unittest
from mock import MagicMock
from litp.core.plan import Plan
from litp.core import constants

def mock_cluster(cluster_id, dependency_list=None):
    cluster = MagicMock()
    cluster.item_id = cluster_id
    cluster.dependency_list = dependency_list
    return cluster

def mock_task(cluster=None):
    task = MagicMock()
    task.state = constants.TASK_INITIAL
    task.group = None
    task._task_node = MagicMock()
    task._task_node.get_cluster = MagicMock(return_value=cluster)
    return task

class TestPlanPhaseSort(unittest.TestCase):
    def setUp(self):
        self.plan = Plan([])
        self.plan._data_manager = MagicMock()

    def test_build_phase_deps_1_phase(self):
        task0 = mock_task()
        self.plan._phases = [[task0]]
        self.plan._build_phase_dependencies()
        self.assertEqual({'0': []},
                         self.plan._required_phases)

    def test_build_phase_deps_no_clusters(self):
        task0 = mock_task()
        task1 = mock_task()
        task2 = mock_task()
        self.plan._phases = [[task0], [task1], [task2]]
        self.plan._build_phase_dependencies()
        self.assertEqual(
            {
                '0': [],
                '1': [0],
                '2': [1]
            },
            self.plan._required_phases
        )

    def test_build_phase_deps_two_phase(self):
        task0 = mock_task()
        task1 = mock_task()
        task2 = mock_task()
        self.plan._phases = [[task0, task1], [task2]]
        self.plan._build_phase_dependencies()
        self.assertEqual({'0': [], '1': [0]}, self.plan._required_phases)

    def test_build_phase_deps_2_same_cluster_phases(self):
        cluster1 = mock_cluster("c1")
        task0 = mock_task()
        task1 = mock_task(cluster1)
        task2 = mock_task(cluster1)
        task3 = mock_task()
        self.plan._phases = [[task0], [task1], [task2], [task3]]
        self.plan._build_phase_dependencies()
        self.assertEqual({'0': [], '1': [0], '2': [1], '3': [2]},
                         self.plan._required_phases)

    def test_build_phase_deps_2_different_cluster_phases(self):
        cluster1 = mock_cluster("c1")
        cluster2 = mock_cluster("c2")
        task0 = mock_task()
        task1 = mock_task(cluster1)
        task2 = mock_task(cluster2)
        task3 = mock_task()
        self.plan._phases = [[task0], [task1], [task2], [task3]]
        self.plan._build_phase_dependencies()
        self.assertEqual({'0': [], '1': [0], '2': [0], '3': [1, 2]},
                         self.plan._required_phases)

    def test_build_phase_deps_just_2_different_cluster_phases(self):
        cluster1 = mock_cluster("c1")
        cluster2 = mock_cluster("c2")
        task0 = mock_task(cluster1)
        task1 = mock_task(cluster2)
        self.plan._phases = [[task0], [task1]]
        self.plan._build_phase_dependencies()
        self.assertEqual({'0': [], '1': []},
                         self.plan._required_phases)

    def test_build_phase_deps_just_2_cluster_phases_with_deps(self):
        cluster1 = mock_cluster("c1")
        cluster2 = mock_cluster("c2", "c1")
        task0 = mock_task(cluster1)
        task1 = mock_task(cluster2)
        self.plan._phases = [[task0], [task1]]
        self.plan._build_phase_dependencies()
        self.assertEqual({'1': [0], '0': []},
                         self.plan._required_phases)

    def test_build_phase_deps_3_cluster_phases_with_deps(self):
        cluster1 = mock_cluster("c1")
        cluster2 = mock_cluster("c2", "c1")
        cluster3 = mock_cluster("c3")
        task0 = mock_task(cluster1)
        task1 = mock_task(cluster2)
        task2 = mock_task(cluster3)
        task3 = mock_task()
        self.plan._phases = [[task0], [task1], [task2], [task3]]
        self.plan._build_phase_dependencies()
        self.assertEqual({'1': [0], '0': [], '3': [1, 2], '2': []},
                         self.plan._required_phases)

    def test_build_phase_deps_3_cluster_mixed_phases_with_multiple_deps(self):
        cluster1 = mock_cluster("c1")
        cluster2 = mock_cluster("c2", "c1,c3")
        cluster3 = mock_cluster("c3")
        task0 = mock_task()
        task1 = mock_task(cluster1)
        taska = mock_task(cluster1)
        taskb = mock_task(cluster3)
        task2 = mock_task(cluster2)
        task3 = mock_task(cluster3)
        task4 = mock_task(cluster3)
        task5 = mock_task()
        self.plan._phases = [
            [task0],  # Not-parallelisable
            [taska, taskb],  # Not-parallelisable
            [task1],  # C1
            [task3],  # C3
            [task4],  # C3
            [task2],  # C2 (depends on C1 and C3)
            [task5]  # Not-parallelisable
        ]
        self.plan._build_phase_dependencies()
        self.assertEqual({
            '0': [],
            '1': [0],
            '2': [1],
            '3': [1],
            '4': [3],
            '5': [2, 4],
            '6': [5]
            },
            self.plan._required_phases
        )

    def test_build_phase_deps_install_like_phases(self):
        cluster1 = mock_cluster("c1")
        cluster2 = mock_cluster("c2")
        task0 = mock_task()
        task1_0 = mock_task(cluster1)
        task1_1 = mock_task(cluster2)
        task2 = mock_task(cluster1)
        task3 = mock_task(cluster2)
        task4 = mock_task()
        self.plan._phases = [
            [task0],  # Not-parallelisable
            [task1_0, task1_1],  # Not-parallelisable
            [task2],  # C1
            [task3],  # C2
            [task4]  # Not-parallelisable
        ]
        self.plan._build_phase_dependencies()
        self.assertEqual(
            {
                '0': [],
                '1': [0],
                '2': [1],
                '3': [1],
                '4': [2, 3]
            },
            self.plan._required_phases
        )

    def test_build_phase_deps_enm_like_cluster_phases(self):
        db_cluster = mock_cluster("db")
        svc_cluster = mock_cluster("svc", "db")
        scp_cluster = mock_cluster("scp", "svc")
        str_cluster = mock_cluster("str", "svc")
        evt_cluster = mock_cluster("evt", "svc")
        task0 = mock_task()
        task1 = mock_task(db_cluster)
        task2 = mock_task(svc_cluster)
        task3 = mock_task(scp_cluster)
        task4 = mock_task(str_cluster)
        task5 = mock_task(evt_cluster)
        task6 = mock_task()
        self.plan._phases = [
            [task0],  # Not-parallelisable
            [task1],  # DB
            [task2],  # SVC depends on DB
            [task3],  # SCP depends on SVC
            [task4],  # STR depends on SVC
            [task5],  # EVT depends on SVC
            [task6]  # Not-parallelisable
        ]
        self.plan._build_phase_dependencies()
        self.assertEqual(
            {
                '0': [],
                '1': [0],
                '2': [1],
                '3': [2],
                '4': [2],
                '5': [2],
                '6': [3, 4, 5]
            },
            self.plan._required_phases
        )

    def test_build_phase_deps_with_hosts_tasks(self):
        svc_cluster = mock_cluster("svc", "db")
        task0 = mock_task()
        # Mock host task assciated with node on svc cluster but on MS node
        host_task1 = mock_task(svc_cluster)
        host_task1.node.get_cluster.return_value = None # No cluster for MS node
        task2 = mock_task(svc_cluster)
        self.plan._phases = [
            [task0],  # Not-parallelisable
            [host_task1],  # MS task
            [task2]  # SVC
        ]
        self.plan._build_phase_dependencies()
        self.assertEqual(
            {
                '0': [],
                '1': [0],
                '2': [1]
            },
            self.plan._required_phases
        )


class TestPlanReadyPhases(unittest.TestCase):
    def setUp(self):
        self.plan = Plan([])
        self.plan._data_manager = MagicMock()
        self.plan._required_phases = {
            '0': set([]),
            '1': set([0]),
            '2': set([1]),
            '3': set([2]),
            '4': set([3]),
            '5': set([4]),
            '6': set([5]),
            '7': set([6]),
            '8': set([7]),  # Four phases require this phase
            '9': set([8]),
            '10': set([9]),
            '11': set([10]),
            '12': set([11]),
            '13': set([12]),
            '14': set([13]),
            '15': set([8]),
            '16': set([15]),
            '17': set([16]),
            '18': set([17]),
            '19': set([18]),
            '20': set([19]),
            '21': set([8]),
            '22': set([21]),
            '23': set([22]),
            '24': set([23]),
            '25': set([24]),
            '26': set([25]),
            '27': set([8]),
            '28': set([27]),
            '29': set([28]),
            '30': set([29]),
            '31': set([30]),
            '32': set([31]),
        }

        for _ in self.plan._required_phases:
            self.plan._phases.append([mock_task(), mock_task()])

    def test_first_phase(self):
        self.assertEquals(set([0]), self.plan.ready_phases(-1))

    def test_second_phase_first_phase_not_over(self):
        self.plan._phases[0][0].state = constants.TASK_SUCCESS
        self.plan._phases[0][1].state = constants.TASK_RUNNING
        self.assertEquals(set([]), self.plan.ready_phases(0))

    def test_second_phase_first_phase_is_over(self):
        self.plan._phases[0][0].state = constants.TASK_SUCCESS
        self.plan._phases[0][1].state = constants.TASK_SUCCESS
        self.assertEquals(set([1]), self.plan.ready_phases(0))

    def test_parallel_phases(self):
        self.plan._phases[8][0].state = constants.TASK_SUCCESS
        self.plan._phases[8][1].state = constants.TASK_SUCCESS
        self.assertEquals(set([9, 15, 21, 27]), self.plan.ready_phases(8))

    def test_parallel_phase_over_others_ongoing(self):
        self.plan._phases[9][0].state = constants.TASK_SUCCESS
        self.plan._phases[9][1].state = constants.TASK_SUCCESS

        self.plan._phases[15][0].state = constants.TASK_SUCCESS
        self.plan._phases[15][1].state = constants.TASK_RUNNING

        self.plan._phases[21][0].state = constants.TASK_SUCCESS
        self.plan._phases[21][1].state = constants.TASK_RUNNING

        self.plan._phases[27][0].state = constants.TASK_SUCCESS
        self.plan._phases[27][1].state = constants.TASK_RUNNING

        self.assertEquals(set([10]), self.plan.ready_phases(9))

        # Phase 27 is over but we only consider phase 16 as ready for queuing
        self.plan._phases[27][1].state = constants.TASK_SUCCESS
        self.plan._phases[27][1].state = constants.TASK_SUCCESS
        self.plan._phases[15][1].state = constants.TASK_SUCCESS
        self.assertEquals(set([16]), self.plan.ready_phases(15))

        self.assertEquals(set([28]), self.plan.ready_phases(27))


class TestPlanResume(unittest.TestCase):
    def setUp(self):
        self.plan = Plan([])
        self.plan._data_manager = MagicMock()

        self.plan._required_phases = {
            '0': set([]),
            '1': set([0]),
            '2': set([1]),
            '3': set([2]),
            '4': set([3]),  # Four phases require this phase
            # First branch ("cluster 1")
            '5': set([4]),
            '6': set([5]),
            '7': set([6]),
            '8': set([7]),
            '9': set([8]),
            '10': set([9]),
            # Second branch ("cluster 2")
            '11': set([4]),
            '12': set([11]),
            '13': set([12]),
            '14': set([13]),
            '15': set([14]),
            '16': set([15]),
            # Third branch ("cluster 3")
            '17': set([4]),
            '18': set([17]),
            '19': set([18]),
            '20': set([19]),
            '21': set([20]),
            '22': set([21]),
            # "post-cluster phases"
            '23': set([10, 16, 22]),
            '24': set([23]),
            '25': set([24]),
            '26': set([25]),
        }

        for _ in self.plan._required_phases:
            self.plan._phases.append([mock_task(), mock_task()])

    def _initial_conditions(self, successful_phases, failed_phases):
        for phase_idx, phase in enumerate(self.plan._phases):
            if phase_idx in successful_phases:
                for task in phase:
                    task.state = constants.TASK_SUCCESS
                continue

            if phase_idx in failed_phases:
                for task in phase:
                    task.state = constants.TASK_FAILED
                continue

            for task in phase:
                task.state = constants.TASK_INITIAL

    def test_resume_single_failed_phase(self):
        # Set up phase states
        successful_phases = set([0, 1, 2])
        failed_phases= set([3])
        self._initial_conditions(successful_phases, failed_phases)

        ready = self.plan.ready_phases(-1)
        self.assertEqual(ready, set([3]))

        for task in self.plan.phases[3]:
            task.state = constants.TASK_SUCCESS

        ready = self.plan.ready_phases(3)
        self.assertEqual(ready, set([4]))

    def test_resume_single_failed_phase_and_concurrent_successful_phases(self):
        # Set up phase states
        successful_phases = set([0, 1, 2, 3, 4, 5, 6, 17])
        failed_phases= set([11,])
        self._initial_conditions(successful_phases, failed_phases)

        ready = self.plan.ready_phases(-1)
        self.assertEqual(ready, set([11, 18, 7]))

        for task in self.plan.phases[11]:
            task.state = constants.TASK_SUCCESS

        ready = self.plan.ready_phases(11)
        self.assertEqual(ready, set([12]))

    def test_resume_multiple_failed_phases(self):
        # Set up phase states
        successful_phases = set([0, 1, 2, 3, 4,])
        failed_phases= set([5,11, 17])
        self._initial_conditions(successful_phases, failed_phases)

        ready = self.plan.ready_phases(-1)
        expected_resume_phases = set([5, 11, 17])
        self.assertEqual(ready, expected_resume_phases)

        for resumed_phase in ready:
            for task in self.plan.phases[resumed_phase]:
                task.state = constants.TASK_SUCCESS

        ready = self.plan.ready_phases(5)
        self.assertEqual(ready, set([6]))
        #
        ready = self.plan.ready_phases(11)
        self.assertEqual(ready, set([12]))
        #
        ready = self.plan.ready_phases(17)
        self.assertEqual(ready, set([18]))

    def test_resume_multiple_failed_phases_and_concurrent_successful_phase(self):
        # Set up phase states
        successful_phases = set([0, 1, 2, 3, 4, 11])
        failed_phases= set([5, 17])
        self._initial_conditions(successful_phases, failed_phases)

        ready = self.plan.ready_phases(-1)
        expected_resume_phases = set([5, 17, 12])
        self.assertEqual(ready, expected_resume_phases)

        for resumed_phase in ready:
            for task in self.plan.phases[resumed_phase]:
                task.state = constants.TASK_SUCCESS

        ready = self.plan.ready_phases(5)
        self.assertEqual(ready, set([6]))
        #
        ready = self.plan.ready_phases(12)
        self.assertEqual(ready, set([13]))
        #
        ready = self.plan.ready_phases(17)
        self.assertEqual(ready, set([18]))
