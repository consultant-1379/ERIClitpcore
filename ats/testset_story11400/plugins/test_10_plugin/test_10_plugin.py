from litp.core.plugin import Plugin
from litp.core.execution_manager import ConfigTask
from litp.plan_types.deployment_plan import deployment_plan_tags
from litp.core.task import OrderedTaskList

class TestPlugin(Plugin):

    def validate_model(self, plugin_api_context):
        return []

    def create_configuration(self, plugin_api_context):
        tasks = []
        node_tasks = []
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
                       'ms::items', 'plugin_sw_item',
                       tag_name=deployment_plan_tags.BOOT_TAG))
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

        node = plugin_api_context.query('node')[0]
        tasks.append(ConfigTask(node, node.network_interfaces,
                       'node network_interfaces task',
                       'node::network_interfaces', '15'))
        tasks.append(ConfigTask(node, node.storage_profile,
                        'node Storage profile task',
                        'node::storage_profile','16'))
        tasks.append(ConfigTask(node, node.os,'node os task',
                        'node::os','17'))
        tasks.append(ConfigTask(node, node.system,'node system task',
                        'node::system','18'))
        for item in node.query("software-item"):
            tasks.append(ConfigTask(node, item, 'node items task',
                       'node::items', '10'))
        for service in node.query("service-base"):
            tasks.append(ConfigTask(node, service, 'node services task',
                       'node::services', '11',ensure='present',
                        tag_name=deployment_plan_tags.MS_TAG))
        for config in node.query("node-config"):
            tasks.append(ConfigTask(node, config, 'node configs task',
                       'node::configs', '12'))
        for file_system in node.query("file-system-base"):
            tasks.append(ConfigTask(node, file_system, 'node file_systems task',
                       'node::file_systems', '13'))
        for route in node.query("route-base"):
            tasks.append(ConfigTask(node, route, 'node routes task',
                       'node::routes', '14'))

        return tasks

