from litp.core.plugin import Plugin
from litp.core.task import ConfigTask
from litp.core.task import CallbackTask
from litp.core.task import RemoteExecutionTask
from litp.core.task import OrderedTaskList
from litp.core.exceptions import CallbackExecutionException


class DummyBazPlugin(Plugin):
    run = 0

    def __init__(self, *args, **kwargs):
        super(DummyBazPlugin, self).__init__(*args, **kwargs)

    def _mock_function(self, *args, **kwargs):
        pass

    def create_configuration(self, api):
        return self.create_configuration_1(api)

    def create_configuration_1(self, api):
        tasks = []
        for node in sorted(api.query("node")):
            for baz in node.query("baz"):
                if baz.is_initial() or baz.is_updated() or \
                   baz.is_for_removal():
                    tasks.extend([
                        ConfigTask(node, baz, "standalone ConfigTask", "baz", "baz1"),
                    ])
        return tasks

    def create_lock_tasks(self, api, node):
        DummyBazPlugin.run += 1
        if DummyBazPlugin.run < 3:
            ms = api.query("ms")[0]
            return (
                CallbackTask(node, "Lock node %s" % node.item_id, self.cb_lock_unlock),
                CallbackTask(node, "Unlock node %s" % node.item_id, self.cb_lock_unlock),
            )
        else:
            ms = api.query("ms")[0]
            return (
                CallbackTask(node, "Lock node %s" % node.item_id, self.cb_lock_unlock),
                CallbackTask(node, "Unlock node %s" % node.item_id, self.cb_unlock_failed),
            )


    def cb_lock_unlock(self):
        pass

    def cb_unlock_failed(self):
        raise CallbackExecutionException("Failed deliberately")
