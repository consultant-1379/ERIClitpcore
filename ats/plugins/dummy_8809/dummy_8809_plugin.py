from litp.core.plugin import Plugin
from litp.core.task import ConfigTask
from litp.core.task import CallbackTask
from litp.core.task import RemoteExecutionTask
from litp.core.task import OrderedTaskList


class Dummy8809Plugin(Plugin):

    def __init__(self, *args, **kwargs):
        super(Dummy8809Plugin, self).__init__(*args, **kwargs)

    def _mock_function(self, *args, **kwargs):
        pass

    def _wait_for_node(self, *args, **kwargs):
        pass

    def create_configuration(self, api):
        tasks = []

        # Generate bootmgr-like tasks

        node_to_foo = {}
        ms_qi = api.query("ms")[0]
        boot_service_qi = ms_qi.query("boot-service")[0]
        for node in sorted(api.query("node")):
            if node.is_initial():
                # Generate pseudo-install tasks
                cobbler_task = ConfigTask(
                    ms_qi,
                    boot_service_qi,
                    "MS \'\'cobbler\'\' task for {0}".format(node.vpath),
                    "cobbler",
                    node.system.vpath
                )
                #cobbler_task.plugin_name="bootmgr_plugin"

                wait_for_node = CallbackTask(
                    node.system,
                    "Wait for {0} to come up".format(node.vpath),
                    self._wait_for_node,
                    vpath=node.vpath
                )
                # Real "add node" tasks have explicit task-to-task dependencies
                # against the Cobbler tasks set by the bootmgr plugin
                #wait_for_node.requires.add(cobbler_task)
                #wait_for_node.plugin_name="bootmgr_plugin"
                tasks.extend([cobbler_task, wait_for_node])

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

                    cluster = node.get_cluster()
                    if cluster and (cluster.is_updated() or cluster.is_applied()):
                        if not cluster.ha_manager:
                            continue

                        # Cluster-bound tasks have to be CallbackTasks
                        tasks.append(
                            CallbackTask(
                                cluster,
                                "Cluster-bound task for {0}".format(foo.vpath),
                                self._mock_function,
                                # Callback args
                                vpath=foo.vpath
                            )
                        )

        return tasks

    def create_lock_tasks(self, api, node):
        ms = api.query("ms")[0]
        return (
            RemoteExecutionTask([node], ms, "Lock node %s" % node.vpath, "lock_unlock", "lock"),
            RemoteExecutionTask([node], ms, "Unlock node %s" % node.vpath, "lock_unlock", "unlock"),
        )
