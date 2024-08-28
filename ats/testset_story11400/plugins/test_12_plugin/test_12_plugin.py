from litp.core.plugin import Plugin
from litp.core.execution_manager import ConfigTask


class TestPlugin(Plugin):

    def validate_model(self, plugin_api_context):
        return []

    def create_configuration(self, plugin_api_context):
        tasks = []
        node = plugin_api_context.query('node')[0]
        tasks = [
            ConfigTask(node, node.network_interfaces,
                       'node network_interfaces task',
                       'node::network_interfaces', '15'),
            ConfigTask(node, node.storage_profile,
                        'node Storage profile task',
                        'node::storage_profile','16'),
            ConfigTask(node, node.os,'node os task',
                        'node::os','17'),
            ConfigTask(node, node.system,'node system task',
                        'node::system','18'),
        ]
        for item in node.query("software-item"):
            tasks.append(ConfigTask(node, item, 'node items task',
                       'node::items', '10'))
        for service in node.query("service-base"):
            tasks.append(ConfigTask(node, service, 'node services task',
                       'node::services', '11'))
        for config in node.query("node-config"):
            tasks.append(ConfigTask(node, config, 'node configs task',
                       'node::configs', '12'))
        for file_system in node.query("file-system-base"):
            tasks.append(ConfigTask(node, file_system, 'node file_systems task',
                       'node::file_systems', '13'))
        for route in node.query("route-base"):
            tasks.append(ConfigTask(node, route, 'node routes task',
                       'node::routes', '14'))
        for t in tasks:
            if (t.call_type, t.call_id) == ('node::file_systems', '13'):
                t.requires.add(('node::items', '10'))
        return tasks

