from litp.core.plugin import Plugin
from litp.core.task import CallbackTask


class Dummy198142Plugin(Plugin):

    def __init__(self, *args, **kwargs):
        super(Dummy198142Plugin, self).__init__(*args, **kwargs)

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
            tasks.append(
                CallbackTask(node, "Task for %s" % node.hostname, self._noop))
        return tasks

    def create_lock_tasks(self, api, node):
        return (
            CallbackTask(node, "Lock task for %s" % node.hostname, self._lock),
            CallbackTask(node, "Unlock task for %s" % node.hostname, self._unlock)
        )
