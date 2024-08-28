from litp.core.plugin import Plugin
from litp.core.task import ConfigTask
from litp.core.task import CallbackTask


class TaskDependenciesPlugin(Plugin):
    def __init__(self, *args, **kwargs):
        super(TaskDependenciesPlugin, self).__init__(*args, **kwargs)

    def create_configuration(self, api):
        tasks = []

        for node in sorted(api.query("node")):
            for test_item in node.query("test_item"):
                task1 = ConfigTask(node, test_item, "ConfigTask A", "package", "name")
                task2 = ConfigTask(node, node, "ConfigTask B", "node_call_type", 'node_call_id')

                task1.requires = set([node, ('node_call_type', 'node_call_id')])
                # task1.requires.add(task2)
                tasks.extend([task1, task2])

        return tasks
