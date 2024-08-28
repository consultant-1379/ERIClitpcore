
from litp.core.plugin import Plugin
from litp.core.task import OrderedTaskList
from litp.core.task import ConfigTask


class DummyPlugin(Plugin):

    def get_tasks(self, node, item):
        if item.item_id == "s1":
            t1 = ConfigTask(node, item, "", "dummy_task_1", "1")
            t2 = ConfigTask(node, item, "", "dummy_task_2", "2")
            t2.requires.add(t1)
            t3 = ConfigTask(node, item, "", "dummy_task_3", "3")
            t4 = ConfigTask(node, item, "", "dummy_task_4", "4")
            t4.requires.add(t3)
            tasks = [
                t1,
                OrderedTaskList(item, [t2, t3]),
                t4
            ]
        else:
            tasks = []
        return tasks

    def create_configuration(self, api):
        nodes = api.query("node") + api.query("ms")
        tasks = []
        for node in nodes:
            for item in node.query("software-item", is_initial=True):
                tasks.extend(self.get_tasks(node, item))
        return tasks
