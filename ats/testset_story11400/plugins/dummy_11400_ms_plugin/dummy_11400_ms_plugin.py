from litp.core.plugin import Plugin
from litp.core.execution_manager import ConfigTask, CallbackTask


class Dummy11400MsPlugin(Plugin):
    """Return CallbackTask hanging off a ModelItem for each dependency on MS."""

    def validate_model(self, plugin_api_context):
        return []

    def create_configuration(self, api):
        tasks = []
        item = api.query_by_vpath("/ms/items/item")
        service = api.query_by_vpath("/ms/services/service")
        config = api.query_by_vpath("/ms/configs/config")
        file_system = api.query_by_vpath("/ms/file_systems/file_system")
        storage_profile = api.query_by_vpath("/ms/storage_profile")
        route = api.query_by_vpath("/ms/routes/route")
        net_interface = api.query_by_vpath("/ms/network_interfaces/ip1")
        os = api.query_by_vpath("/ms/os")
        system = api.query_by_vpath("/ms/system")

        tasks = [
                CallbackTask(os, 'OS interface callback task', Dummy11400MsPlugin._cb),
                CallbackTask(route, 'Route callback task', Dummy11400MsPlugin._cb),
                CallbackTask(config, 'Config callback task', Dummy11400MsPlugin._cb),
                CallbackTask(storage_profile, 'Storage profile callback task', Dummy11400MsPlugin._cb),
                CallbackTask(file_system, 'Filesystem callback task', Dummy11400MsPlugin._cb),
                CallbackTask(item, 'Item callback task', Dummy11400MsPlugin._cb),
                CallbackTask(system, 'System interface callback task', Dummy11400MsPlugin._cb),
                CallbackTask(service, 'Service callback task', Dummy11400MsPlugin._cb),
                CallbackTask(net_interface, 'Network interface callback task', Dummy11400MsPlugin._cb),
        ]
        return tasks

    def _cb(self, api):
        pass
