from litp.core.plugin import Plugin
from litp.core.execution_manager import ConfigTask, CallbackTask


class Dummy11400MsPlugin(Plugin):
    """Return CallbackTask hanging off a ModelItem for each dependency on MS."""

    def validate_model(self, plugin_api_context):
        return []

    def create_configuration(self, api):
        tasks = []
        ms = api.query('ms')[0]
        net_interface = api.query_by_vpath("/ms/network_interfaces/ip1")
        storage_profile = api.query_by_vpath("/ms/storage_profile")
        os = api.query_by_vpath("/ms/os")
        system = api.query_by_vpath("/ms/system")
        tasks = [
                CallbackTask(os, 'OS interface callback task', Dummy11400MsPlugin._cb),
                CallbackTask(storage_profile, 'Storage profile callback task', Dummy11400MsPlugin._cb),
                CallbackTask(system, 'System interface callback task', Dummy11400MsPlugin._cb),
                CallbackTask(net_interface, 'Network interface callback task', Dummy11400MsPlugin._cb),
        ]
        for item in ms.query("software-item"):
            tasks.append(CallbackTask(item, 'Item callback task', Dummy11400MsPlugin._cb))
        for service in ms.query("service-base"):
            tasks.append(CallbackTask(service, 'Service callback task', Dummy11400MsPlugin._cb))
        for config in ms.query("node-config"):
            tasks.append(CallbackTask(config, 'Config callback task', Dummy11400MsPlugin._cb))
        for file_system in ms.query("file-system-base"):
            tasks.append(CallbackTask(file_system, 'Filesystem callback task', Dummy11400MsPlugin._cb))
        for route in ms.query("route-base"):
            tasks.append(CallbackTask(route, 'Route callback task', Dummy11400MsPlugin._cb))
        return tasks

    def _cb(self, api):
        pass

