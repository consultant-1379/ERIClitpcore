from litp.core.plugin import Plugin
from litp.core.task import ConfigTask
from litp.core.task import CallbackTask
from litp.core.exceptions import CallbackExecutionException


class Dummy11955DevPlugin(Plugin):

    def create_configuration(self, api):
        node = api.query('node')[0]
        cb_task = CallbackTask(node, "Callback Task",  self._cb)
        diff_phase_cf_task = ConfigTask(node, node, "ConfigTask in different phase.", "diff_phase", "diff_phase1")
        cfg_split = ConfigTask(node, node, "Standalone ConfigTask", "baz", "baz1")
        cfg_split.requires.add(cb_task)
        diff_phase_cf_task.requires.add(cfg_split)
        tasks = [cb_task,
                 ConfigTask(node, node, "Standalone ConfigTask", "bar", "bar1"),
                 ConfigTask(node, node, "Standalone ConfigTask", "foo", "foo1"),
                 cfg_split,
                 diff_phase_cf_task]

        for item in node.network_interfaces:
            if item.is_initial():
                tasks.append(ConfigTask(node, node.network_interfaces, 'node install network_interfaces task','node::network_interfaces', 'id_node_net'))
            if node.system.is_initial():
                tasks.append(ConfigTask(node, node.system, 'node install system task','node::system', 'id_node_system'))
        return tasks

    def _cb(self, api):
        pass
