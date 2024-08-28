from litp.core.plugin import Plugin
from litp.core.task import Task
from litp.core.task import ConfigTask
from litp.core.task import CallbackTask
from litp.plan_types.deployment_plan import deployment_plan_groups


class IncompleteTaskDependenciesPlugin(Plugin):
    def __init__(self, *args, **kwargs):
        super(IncompleteTaskDependenciesPlugin, self).__init__(*args, **kwargs)

    def create_configuration(self, api):

        for node in sorted(api.query("node")):
            for test_item in node.query("test_item"):
                task1 = ConfigTask(node, test_item, "ConfigTask A", "package", "name")
                task2 = ConfigTask(node, node, "ConfigTask B", "node_call_type", 'node_call_id')

                task2.requires = set([task1])
                # This is a hacky hack
                task1.group = deployment_plan_groups.NODE_GROUP

        return [task2]
