from litp.core.plugin import Plugin
from litp.core.execution_manager import ConfigTask


class TestPlugin(Plugin):

    def validate_model(self, plugin_api_context):
        return []

    def create_configuration(self, plugin_api_context):
        tasks = []
        ms = plugin_api_context.query('ms')[0]
        tasks = [
            ConfigTask(ms, ms.items, 'ms collection:items task',
                       'ms::items', '1'),
            ConfigTask(ms, ms.network_interfaces,
                       'ms collection:network_interfaces task',
                       'ms::network_interfaces', '6'),
            ConfigTask(ms, ms.system,'ms collection:system task',
                        'ms::system','9'),
            ConfigTask(ms, ms.routes, 'ms collection:routes task',
                       'ms::routes', '2'),
            ConfigTask(ms, ms.services, 'ms collection:services task',
                       'ms::services', '3'),
            ConfigTask(ms, ms.configs, 'ms collection:configs task',
                       'ms::configs', '4'),
            ConfigTask(ms, ms.file_systems, 'ms collection:file_systems task',
                       'ms::file_systems', '5'),
            #ConfigTask(ms, ms.os,'ms os task',
            #            'ms::os','8'),
        ]
        return tasks
