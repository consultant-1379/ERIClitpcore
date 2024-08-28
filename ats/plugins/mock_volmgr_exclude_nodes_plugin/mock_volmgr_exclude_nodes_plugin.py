from litp.core.plugin import Plugin
from litp.core.execution_manager import CallbackTask


class MockVolmgrExcludeNodesPlugin(Plugin):
    """
    LITP Mock volmgr plugin to provide snapshots tasks in ats
    """

    def create_configuration(self, api):
        return []

    def create_snapshot_plan(self, api):
        tasks = []
        if api.snapshot_action() == 'create':
            tasks.extend(self._create_snapshot(api))
        elif api.snapshot_action() == 'remove':
            tasks.extend(self._remove_snapshot(api))
        return tasks

    def _create_snapshot(self, api):
        tasks = []
        nodes = api.query("node") + \
                api.query("ms")
        nodes = [node for node in nodes if node not in api.exclude_nodes]
        for node in nodes:
            description = 'create snapshot node: {0}'.format(node.hostname)
            tasks.append(
                CallbackTask(node, description, self._do_create)
            )
        return tasks

    def _remove_snapshot(self, api):
        tasks = []
        nodes = api.query("node") + \
                api.query("ms")
        nodes = [node for node in nodes if node not in api.exclude_nodes]
        for node in nodes:
            description = 'remove snapshot node: {0}'.format(node.hostname)
            tasks.append(
                CallbackTask(node, description, self._do_remove)
            )
        return tasks

    def _do_create(self, callback_api):
        return

    def _do_remove(self, callback_api):
        return
