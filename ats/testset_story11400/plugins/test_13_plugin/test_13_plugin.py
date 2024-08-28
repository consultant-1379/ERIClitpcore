from litp.core.plugin import Plugin
from litp.core.execution_manager import ConfigTask


class TestPlugin(Plugin):

    def validate_model(self, plugin_api_context):
        return []

    def create_configuration(self, plugin_api_context):
        tasks = []
        ms = plugin_api_context.query('ms')[0]
        tasks = [
            ConfigTask(ms, ms.network_interfaces,
                       'ms network_interfaces task',
                       'ms::network_interfaces', '6'),
            ConfigTask(ms, ms.storage_profile,'ms Storage profile task',
                        'ms::storage_profile','7'),
            ConfigTask(ms, ms.os,'ms os task',
                        'ms::os','8'),
            ConfigTask(ms, ms.system,'ms system task',
                        'ms::system','9'),
        ]
        for item in ms.query("software-item"):
            tasks.append(ConfigTask(ms, item, 'ms items task',
                       'ms::items', '1'))
        for service in ms.query("service-base"):
            tasks.append(ConfigTask(ms, service, 'ms services task',
                       'ms::services', '3'))
        for config in ms.query("node-config"):
            tasks.append(ConfigTask(ms, config, 'ms configs task',
                       'ms::configs', '4'))
        for file_system in ms.query("file-system-base"):
            tasks.append(ConfigTask(ms, file_system, 'ms file_systems task',
                       'ms::file_systems', '5'))
        for route in ms.query("route-base"):
            tasks.append(ConfigTask(ms, route, 'ms routes task',
                       'ms::routes', '2'))
        tasks[6].requires.add(('ms::items', '1'))
        return tasks
