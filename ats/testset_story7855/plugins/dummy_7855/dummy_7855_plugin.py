from litp.core.plugin import Plugin
from litp.core.task import ConfigTask
from litp.core.task import CallbackTask
from litp.core.task import RemoteExecutionTask
from litp.core.task import OrderedTaskList
from litp.core.exceptions import CallbackExecutionException


class Dummy7855Plugin(Plugin):

    def __init__(self, *args, **kwargs):
        super(Dummy7855Plugin, self).__init__(*args, **kwargs)

    def create_configuration(self, api):
        tasks = []
        for node in sorted(api.query("node")):
            for baz in node.query("baz"):
                if baz.is_initial() or baz.is_updated() or \
                   baz.is_for_removal():
                    tasks.extend([
                        ConfigTask(node, baz, "standalone ConfigTask", "baz", "baz1"),
                    ])
            # Return 2 CallbackTask in separate phases hanging off cluster
            for foo in node.query("foo"):
                cluster = api.query_by_vpath("/deployments/local/clusters/cluster1")
                if cluster and (foo.is_initial() or foo.is_applied()):
                    cft_foo = ConfigTask(node, foo, "Foo ConfigTask", "foo", "foo_one")
                    cb = CallbackTask(cluster, "First CallbackTask", self._cb)
                    cb_2 = CallbackTask(cluster, "Second CallbackTask", self._cb_two)
                    cb_2.requires.add(cb)
                    tasks.extend([cb, cb_2, cft_foo])

            # Return 2 task associate with an item and one that isnt
            bar_tasks = []
            for bar in node.query("bar"):
                cluster = api.query_by_vpath("/deployments/local/clusters/cluster1")
                if cluster and (bar.is_initial() or bar.is_applied()):
                    cft_bar = ConfigTask(node, bar, "Bar ConfigTask", "bar", "bar_one")
                    cb_bar = CallbackTask(cluster, "First CallbackTask", self._cb_three)
                    cb_bar_2 = CallbackTask(cluster, "Second CallbackTask", self._cb_four)
                    cb_bar_2.requires.add(cb_bar)
                    cb_bar_3 = CallbackTask(node.parent, "Unrelated CallbackTask", self.cb_fail)
                    cb_bar_3.requires.add(cb_bar_2)
                    bar_tasks.extend([cb_bar, cb_bar_2, cft_bar, cb_bar_3])
            if bar_tasks:
                return bar_tasks

        return tasks

    def create_lock_tasks(self, api, node):
        return (
            CallbackTask(node, "Lock node %s" % node.item_id, self.cb_fail),
            CallbackTask(node, "Unlock node %s" % node.item_id, self.cb_lock_unlock),
        )

    def _cb(self):
        pass

    def _cb_two(self):
        pass

    def _cb_three(self):
        pass

    def _cb_four(self):
        pass

    def cb_lock_unlock(self):
        pass

    def cb_fail(self):
        raise CallbackExecutionException("Failed deliberately")
