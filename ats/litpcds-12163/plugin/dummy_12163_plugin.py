from litp.core.plugin import Plugin
from litp.core.task import ConfigTask
from litp.core.task import CallbackTask
from litp.core.task import RemoteExecutionTask


class Dummy12163Plugin(Plugin):

    def __init__(self, *args, **kwargs):
        super(Dummy12163Plugin, self).__init__(*args, **kwargs)

    def _lock(self, callback_api):
        pass

    def _unlock(self, callback_api):
        pass

    def create_configuration(self, api):
        return []

    def create_lock_tasks(self, api, node):
        return (
            CallbackTask(node, "Lock task for %s" % node.hostname, self._lock),
            CallbackTask(node, "Unlock task for %s" % node.hostname, self._unlock)
        )
