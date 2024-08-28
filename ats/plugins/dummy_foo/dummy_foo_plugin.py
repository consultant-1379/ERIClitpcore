from litp.core.plugin import Plugin
from litp.core.task import ConfigTask
from litp.core.task import CallbackTask
from litp.core.task import RemoteExecutionTask
from litp.core.task import OrderedTaskList


class DummyFooPlugin(Plugin):
    run = 0

    def __init__(self, *args, **kwargs):
        super(DummyFooPlugin, self).__init__(*args, **kwargs)

    def _mock_function(self, *args, **kwargs):
        pass

    def create_configuration(self, api):
        self.run += 1
        if self.run == 1:
            return self.create_configuration_1(api)
        elif self.run == 2:
            return self.create_configuration_2(api)
        else:
            return []

    def create_configuration_1(self, api):
        tasks = []
        for node in sorted(api.query("node")):
            for foo in node.query("foo"):
                if foo.is_initial() or foo.is_updated() or \
                   foo.is_for_removal():
                    tasks.extend([
                        ConfigTask(node, foo, "standalone ConfigTask", "foo", "foo1"),
                    ])
        return tasks

    def create_configuration_2(self, api):
        tasks = []

        node_to_foo = {}
        for node in sorted(api.query("node")):
            for foo in node.query("foo"):
                if foo.is_initial() or foo.is_updated() or \
                   foo.is_for_removal():
                    if node not in node_to_foo:
                        node_to_foo[node] = []
                    node_to_foo[node].append(foo)
                    tasks.extend([
                        ConfigTask(node, foo, "standalone ConfigTask", "foo", "foo1"),
                        ConfigTask(node, node, "standalone ConfigTask", "foo", "foo2"),
                    ])

        if node_to_foo:
            ms = api.query("ms")[0]
            for node, foos in node_to_foo.iteritems():
                ordered_tasks = []
                for foo in foos:
                    ordered_tasks.extend([
                        ConfigTask(
                            node, foo, "ordered ConfigTask 1", "foo", "foo3"),
                        ConfigTask(
                            node, foo, "ordered ConfigTask 2", "foo", "foo4"),
                        CallbackTask(
                            foo, "ordered CallbackTask", self._mock_function, "foo5"),
                        ConfigTask(
                            node, foo, "ordered ConfigTask 3", "foo", "foo6"),
                    ])
                tasks.extend([
                    OrderedTaskList(
                        ms, ordered_tasks)
                ])
            for node in node_to_foo.keys():
                tasks.append(RemoteExecutionTask(
                    [node], ms, "RemoteExecutionTask (%s)" % node.item_id,
                    "action", "agent"))

        return tasks

    def create_lock_tasks(self, api, node):
        ms = api.query("ms")[0]
        return (
            RemoteExecutionTask([node], ms, "Lock node %s" % node.item_id, "lock_unlock", "lock"),
            RemoteExecutionTask([node], ms, "Unlock node %s" % node.item_id, "lock_unlock", "unlock"),
        )

