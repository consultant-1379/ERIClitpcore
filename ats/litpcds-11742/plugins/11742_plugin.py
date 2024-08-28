from litp.core.plugin import Plugin
from litp.core.task import CallbackTask, ConfigTask
from litp.core.exceptions import CallbackExecutionException


class Dummy11742Plugin(Plugin):

    def _failing_cb(self, callback_api):
        raise CallbackExecutionException("Oh noes :(")

    def create_configuration(self, api):
        tasks = []
        ms = api.query("ms")[0]

        networks = api.query_by_vpath("/infrastructure/networking/networks")
        mgmt_net_name = networks.query("network", litp_management="true")[0].name

        mgmt_ifs = []
        for node_mgmt_if in api.query("network-interface", network_name=mgmt_net_name):
            node = node_mgmt_if.parent.parent
            if node.is_ms():
                continue
            mgmt_ifs.append(node_mgmt_if)
            tasks.append(ConfigTask(node, node_mgmt_if, "Net task", "foo", "bar"))

        # Create a failing CallbackTask
        failing_task = CallbackTask(ms, "Failing task", self._failing_cb)
        failing_task.model_items |= set(
            [mgmt_if for mgmt_if in mgmt_ifs if mgmt_if.applied_properties_determinable]
        )

        tasks.append(failing_task)
        return tasks
