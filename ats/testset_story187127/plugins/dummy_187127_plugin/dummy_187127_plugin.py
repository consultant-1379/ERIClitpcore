from litp.core.plugin import Plugin
from litp.core.task import ConfigTask
from litp.core.task import CallbackTask


class Dummy187127Plugin(Plugin):

    def create_configuration(self, api):
        deconfig_tasks = []
        config_tasks = []
        for node in api.query("node") + api.query("ms"):
            for task_item in node.query("software-item"):
                if task_item.is_initial():
                    config_tasks.append(
                        CallbackTask(task_item, "->Applied CallbackTask", self._noop_callback)
                    )
                elif task_item.is_for_removal():
                    config_tasks.append(
                        CallbackTask(task_item, "->Removed CallbackTask", self._noop_callback)
                    )
        return deconfig_tasks + config_tasks

    def create_lock_tasks(self, api, node):
        ms = api.query("ms")[0]
        return (
            CallbackTask(node, "Lock CallbackTask", self._noop_callback),
            CallbackTask(node, "Unlock CallbackTask", self._noop_callback)
        )

    def create_snapshot_plan(self, api):
        tasks = []
        if api.snapshot_action() == 'create':
            nodes = api.query('node') + api.query('ms')
            for node in nodes:
                snap_task = CallbackTask(
                    node, "Snapshot creation task", self._noop_callback
                )
                tasks.append(snap_task)

        return tasks

    def _noop_callback(self, api):
        pass
