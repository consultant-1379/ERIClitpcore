from litp.core.plugin import Plugin
from litp.core.task import ConfigTask
from litp.core.task import CallbackTask
from litp.core.exceptions import CallbackExecutionException


class FailedCallbackPlugin(Plugin):

    def create_configuration(self, api):
        node = api.query('node')[0]
        failing_cb_task = CallbackTask(node, "Callback Task which fails: %s" % node.item_id, self.cb_fail)
        diff_phase_cf_task = ConfigTask(node, node, "ConfigTask in different phase.", "diff_phase", "diff_phase1")
        CB_depend_task = ConfigTask(node, node, "Standalone ConfigTask", "baz", "baz1")
        failing_cb_task.requires.add(CB_depend_task)
        diff_phase_cf_task.requires.add(failing_cb_task)
        return [failing_cb_task,
                CB_depend_task,
                ConfigTask(node, node, "Standalone ConfigTask", "bar", "bar1"),
                ConfigTask(node, node, "Standalone ConfigTask", "foo", "foo1"),
                diff_phase_cf_task]

    def cb_fail(self, api):
        raise CallbackExecutionException("Failed deliberately")

