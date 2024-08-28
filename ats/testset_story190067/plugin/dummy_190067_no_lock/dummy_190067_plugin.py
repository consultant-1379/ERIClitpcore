from litp.core.plugin import Plugin
from litp.core.task import CallbackTask


class Dummy190067NoLockPlugin(Plugin):

    def __init__(self, *args, **kwargs):
        super(Dummy190067NoLockPlugin, self).__init__(*args, **kwargs)

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
