from litp.core.plugin import Plugin
from litp.core.task import ConfigTask
from litp.core.task import CallbackTask
from litp.core.task import RemoteExecutionTask


class Dummy12114Plugin(Plugin):

    def __init__(self, *args, **kwargs):
        super(Dummy12114Plugin, self).__init__(*args, **kwargs)

    def _lock(self, callback_api):
        pass

    def _unlock(self, callback_api):
        pass

    def create_configuration(self, api):
        tasks = []
        # Generate package tasks for install and removal
        for cluster in api.query("cluster"):
            nodes = cluster.query("node")
            cluster_tasks = []

            for svc in cluster.services:
                for svc_app in svc.applications:
                    for app_pkg in svc_app.packages:
                        if app_pkg.is_initial():
                            for svc_node in nodes:
                                cluster_tasks.append(ConfigTask(
                                    svc_node,
                                    app_pkg,
                                    "Install %s on %s" % (app_pkg.name, svc_node.hostname),
                                    "package",
                                    app_pkg.name,
                                    ensure="present"
                                ))
                        elif app_pkg.is_for_removal():
                            for svc_node in nodes:
                                cluster_tasks.append(ConfigTask(
                                    svc_node,
                                    app_pkg,
                                    "Remove %s on %s" % (app_pkg.name, svc_node.hostname),
                                    "package",
                                    app_pkg.name,
                                    ensure="absent"
                                ))

            tasks.extend(cluster_tasks)

            for node in nodes:
                node_task = None
                for node_pkg in node.query("package"):
                    if node_pkg.is_initial():
                        node_task = ConfigTask(
                            node,
                            node_pkg,
                            "Install %s" % node_pkg.name,
                            "package",
                            node_pkg.name,
                            ensure="present"
                        )
                    elif node_pkg.is_for_removal():
                        node_task = ConfigTask(
                            node,
                            node_pkg,
                            "Remove %s" % node_pkg.name,
                            "package",
                            node_pkg.name,
                            ensure="absent"
                        )

                    if node_task and node_pkg.plugin_deps == "true":
                        node_task.requires |= set(cluster_task for cluster_task in cluster_tasks if cluster_task.node == node)

                tasks.append(node_task)

        return tasks

    def create_lock_tasks(self, api, node):
        return (
            CallbackTask(node, "Lock task for %s" % node.hostname, self._lock),
            CallbackTask(node, "Unlock task for %s" % node.hostname, self._unlock)
        )
