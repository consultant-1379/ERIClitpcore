from litp.core.plugin import Plugin
from litp.core.task import ConfigTask
from litp.core.task import CallbackTask
from litp.core.task import RemoteExecutionTask
from litp.core.task import OrderedTaskList


class DummyBarPlugin(Plugin):
    def __init__(self, *args, **kwargs):
        super(DummyBarPlugin, self).__init__(*args, **kwargs)

    def _mock_function(self, *args, **kwargs):
        pass

    def create_configuration(self, api):
        return self.create_configuration_1(api)

    def create_configuration_1(self, api):
        tasks = []
        for node in sorted(api.query("node")):
            for bar in node.query("bar"):
                if bar.is_initial() or bar.is_updated() or \
                   bar.is_for_removal():
                    tasks.extend([
                        ConfigTask(node, bar, "standalone ConfigTask", "bar", "bar1"),
                    ])
        return tasks

    def create_lock_tasks(self, api, node):
        ms = api.query("ms")[0]
        return (
            ConfigTask(ms, node, "lock ConfigTask", "node_lock", "blah1"),
            ConfigTask(ms, node, "unlock ConfigTask", "node_unlock", "blah2"),
        )

