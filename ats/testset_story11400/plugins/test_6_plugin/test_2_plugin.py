from litp.core.plugin import Plugin
from litp.core.execution_manager import ConfigTask


class TestPlugin(Plugin):

    def validate_model(self, plugin_api_context):
        return []

    def create_configuration(self, plugin_api_context):
        tasks = []
        for node in sorted(plugin_api_context.query("node")):
            task10 = ConfigTask(node, node.items, "node items Collection task", "node::items", "10")
            task11 = ConfigTask(node, node.services, "node services Collection task", "node::services", "11")
            task12 = ConfigTask(node, node.configs, "node configs Collection task", "node::configs", '12')
            task13 = ConfigTask(node, node.file_systems, "node file_systems Collection task", "node::file_systems", '13')
            task14 = ConfigTask(node, node.routes, "nodes routes Collection task", "node::routes", "14")
            task15 = ConfigTask(node, node.network_interfaces, 'node network_interfaces Collection task','node::network_interfaces', '15')
            task16 = ConfigTask(node, node.storage_profile, "node Storage_profile Collection task", "node::storage_profile", '16')
            task17 = ConfigTask(node, node.os, "nodes os Collection task", "node::os", "17")
            task18 = ConfigTask(node, node.system, 'node system Collection task','node::system', '18')
            tasks.extend([task10, task11, task12, task13, task14, task15, task16, task17, task18])
        return tasks

