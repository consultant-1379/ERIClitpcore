from litp.core.plugin import Plugin
from litp.core.task import ConfigTask


class InitialNodeTasksOnlyPlugin(Plugin):
    def __init__(self, *args, **kwargs):
        super(InitialNodeTasksOnlyPlugin, self).__init__(*args, **kwargs)

    def create_configuration(self, api):
        tasks = []
        nodes = api.query("node") + api.query("ms")
        for node in nodes:
            if node.is_initial():
                tasks.extend([
                    ConfigTask(node, node, "ConfigTask", "foo", node.hostname),
                ])
        return tasks
