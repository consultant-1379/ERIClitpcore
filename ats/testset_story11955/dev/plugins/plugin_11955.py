from litp.core.plugin import Plugin
from litp.core.execution_manager import ConfigTask, CallbackTask


class Dummy11955Plugin(Plugin):
    """Return CallbackTask hanging off a ModelItem for each dependency on Node."""

    def validate_model(self, plugin_api_context):
        return []

    def create_configuration(self, api):
        tasks = []
        node = api.query('node')[0]
        storage_profile = api.query_by_vpath("/deployments/local/clusters/cluster1/nodes/node1/storage_profile")
        net_interface = api.query_by_vpath("/deployments/local/clusters/cluster1/nodes/node1/network_interfaces/ip1")
        os = api.query_by_vpath("/deployments/local/clusters/cluster1/nodes/node1/os")
        system = api.query_by_vpath("/deployments/local/clusters/cluster1/nodes/node1/system")

        tasks = [
                CallbackTask(os, 'OS interface callback task', Dummy11955Plugin._cb),
                CallbackTask(storage_profile, 'Storage profile callback task', Dummy11955Plugin._cb),
                CallbackTask(system, 'System interface callback task', Dummy11955Plugin._cb),
                CallbackTask(net_interface, 'Network interface callback task', Dummy11955Plugin._cb),
        ]
        for item in node.query("software-item"):
            tasks.append(CallbackTask(item, 'Item callback task', Dummy11955Plugin._cb))
        for service in node.query("service-base"):
            tasks.append(CallbackTask(service, 'Service callback task', Dummy11955Plugin._cb))
        for config in node.query("node-config"):
            tasks.append(CallbackTask(config, 'Config callback task', Dummy11955Plugin._cb))
        for file_system in node.query("file-system-base"):
            tasks.append(CallbackTask(file_system, 'Filesystem callback task', Dummy11955Plugin._cb))
        for route in node.query("route-base"):
            tasks.append(CallbackTask(route, 'Route callback task', Dummy11955Plugin._cb))
        return tasks

    def _cb(self, api):
        pass


