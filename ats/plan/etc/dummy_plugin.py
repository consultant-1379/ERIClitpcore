
from litp.core.plugin import Plugin
from litp.core.task import OrderedTaskList
from litp.core.task import ConfigTask
from litp.core.task import CallbackTask


class DummyPlugin(Plugin):
    def _mock_function(self, *args):
        pass

    def get_tasks(self, node, package):
        if package.item_id == "vim1":
            tasks = [
                ConfigTask(node, package, "", "dummy_task_1", "1"),
                OrderedTaskList(package, [
                    ConfigTask(
                        node, package, "", "dummy_task_2", "2"),
                    ConfigTask(
                        node, package, "", "dummy_task_3", "3"),
                    ConfigTask(
                        node, package, "", "dummy_task_4", "4"),
                ]),
                ConfigTask(node, package, "", "dummy_task_5", "5"),
            ]
        elif package.item_id == "vim2":
            tasks = [
                ConfigTask(node, package, "", "dummy_task_1", "1"),
                OrderedTaskList(package, [
                    ConfigTask(
                        node, package, "", "dummy_task_2", "2"),
                    ConfigTask(
                        node, package, "", "dummy_task_3", "3"),
                    CallbackTask(
                        node, "dummy_task_4", self._mock_function, "4"),
                    ConfigTask(
                        node, package, "", "dummy_task_5", "5"),
                    ConfigTask(
                        node, package, "", "dummy_task_6", "6"),
                ]),
                ConfigTask(node, package, "", "dummy_task_7", "7"),
            ]
        elif package.item_id == "vim3":
            tasks = [
                ConfigTask(node, node.system.query("disk")[0], "", "dummy_task_1_1", "1_1"),
                ConfigTask(node, node.system.query("disk")[0], "", "dummy_task_1_2", "1_2"),
                ConfigTask(node, node.system, "", "dummy_task_2_1", "2_1"),
                ConfigTask(node, node.system, "", "dummy_task_2_2", "2_2"),
                OrderedTaskList(node.os, [
                    ConfigTask(
                        node, node.os, "", "dummy_task_3_1", "3_1"),
                    ConfigTask(
                        node, node.os, "", "dummy_task_3_2", "3_2"),
                    CallbackTask(
                        node.os, "dummy_task_4_1", self._mock_function, "4_1"),
                    ConfigTask(
                        node, node.os, "", "dummy_task_5_1", "5_1"),
                    ConfigTask(
                        node, node.os, "", "dummy_task_5_2", "5_2"),
                ]),
                ConfigTask(node, node, "", "dummy_task_6_1", "6_1"),
                ConfigTask(node, node, "", "dummy_task_6_2", "6_2"),
            ]
        else:
            tasks = []
        return tasks

    def create_configuration(self, api):
        nodes = api.query("node")
        tasks = []
        for node in nodes:
            for package in api.query("mock-package", is_initial=True):
                tasks.extend(self.get_tasks(node, package))
        return tasks
