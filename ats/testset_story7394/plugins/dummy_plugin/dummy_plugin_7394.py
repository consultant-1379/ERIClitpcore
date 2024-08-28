from litp.core.plugin import Plugin
from litp.core.task import ConfigTask
from litp.core.task import CallbackTask
from litp.core.task import OrderedTaskList


class DummyPlugin(Plugin):
    def _cb1(self, *args, **kwargs):
        pass

    def _cb2(self, *args, **kwargs):
        pass

    def create_configuration(self, api):
        dummy_packages = api.query("dummy-package")
        if dummy_packages[0].item_id == "foo_01":
            return self.create_configuration_tc01(api)
        elif dummy_packages[0].item_id == "foo_02":
            return self.create_configuration_tc02(api)
        elif dummy_packages[0].item_id == "foo_03":
            return self.create_configuration_tc03(api)
        return []

    def create_configuration_tc01(self, api):
        tasks = []
        ms = api.query("ms")[0]
        for dummy_package in ms.query("dummy-package"):
            if dummy_package.is_applied():
                continue
            tasks.extend([
                ConfigTask(
                    ms, dummy_package,
                    "ConfigTask call_type_1",
                    "call_type_1", "foo",
                    name=dummy_package.name
                ),
                ConfigTask(
                    ms, dummy_package,
                    "ConfigTask call_type_2",
                    "call_type_2", "foo",
                    name=dummy_package.name
                )
            ])
        return tasks

    def create_configuration_tc02(self, api):
        tasks = []
        ms = api.query("ms")[0]
        node2 = api.query_by_vpath("/deployments/site1/clusters/cluster1/nodes/node2")
        for dummy_package in ms.query("dummy-package"):
            if dummy_package.is_applied():
                continue

            task1 = CallbackTask(
                dummy_package, "CallbackTask _cb1",
                self._cb1
            )
            task2 = ConfigTask(
                ms, dummy_package,
                "ConfigTask call_type_1",
                "call_type_1", "foo"
            )
            task3 = CallbackTask(
                dummy_package, "CallbackTask _cb2",
                self._cb2
            )
            task4 = ConfigTask(
                ms, dummy_package,
                "ConfigTask call_type_2",
                "call_type_2", "foo"
            )
            tasks.append(
                OrderedTaskList(ms, [task1, task2, task3, task4])
            )
        # Fail this task, which is associated with a separate model item
        task5 = ConfigTask(
            node2, node2,
            "Fail ConfigTask Hanging Off Node",
            "node_call_type", "node_id"
        )
        tasks.append(task5)
        return tasks

    def create_configuration_tc03(self, api):
        tasks = []
        ms = api.query("ms")[0]
        node2 = api.query_by_vpath("/deployments/site1/clusters/cluster1/nodes/node2")
        for dummy_package in ms.query("dummy-package"):
            if dummy_package.is_applied():
                continue

            task1 = CallbackTask(
                dummy_package, "CallbackTask _cb1",
                self._cb1
            )
            task2 = ConfigTask(
                ms, dummy_package,
                "ConfigTask call_type_1",
                "call_type_1", "foo"
            )
            task2.requires.add(task1)
            task3 = CallbackTask(
                dummy_package, "CallbackTask _cb2",
                self._cb2
            )
            task3.requires.add(task2)
            task4 = ConfigTask(
                ms, dummy_package,
                "ConfigTask call_type_2",
                "call_type_2", "foo"
            )
            task4.requires.add(task3)
            tasks.extend([task1, task2, task3, task4])
        # Fail this task, which is associated with a separate model item
        task5 = ConfigTask(
            node2, node2,
            "Fail ConfigTask Hanging Off Node",
            "node_call_type", "node_id"
        )
        tasks.append(task5)
        return tasks
