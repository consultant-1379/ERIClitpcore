from litp.core.plugin import Plugin
from litp.core.task import CallbackTask


class Dummy190067LockPlugin(Plugin):

    def __init__(self, *args, **kwargs):
        super(Dummy190067LockPlugin, self).__init__(*args, **kwargs)

    def _lock(self, callback_api):
        pass

    def _unlock(self, callback_api):
        pass

    def _noop(self, callback_api):
        pass

    def create_configuration(self, api):
        tasks = []

        nodes = api.query('node')
        for node in nodes:
            for disk in node.query('disk'):
                if disk.is_updated():
                    task = CallbackTask(node, "no-op task for disk uuid %s" % disk.uuid, self._noop),
                    tasks.extend(task)
        return tasks

    def create_lock_tasks(self, api, node):
        return (
            CallbackTask(node, "Lock task for %s" % node.hostname, self._lock),
            CallbackTask(node, "Unlock task for %s" % node.hostname, self._unlock)
        )
