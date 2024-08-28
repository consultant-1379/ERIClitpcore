from litp.core.plugin import Plugin
from litp.core.execution_manager import ConfigTask
from litp.core.execution_manager import RemoteExecutionTask

class TestPlugin(Plugin):

    def validate_model(self, plugin_api_context):
        return []

    def create_configuration(self, plugin_api_context):
        tasks = []
        ms = plugin_api_context.query('ms')[0]
        for item in ms.file_systems:
            if item.is_applied():
                 task1 = ConfigTask(ms, ms.file_systems, 'ms upgrade file_systems task',
                          'ms::file_systems', 'up_ms_file')
                 tasks.append(task1)
        for item in ms.network_interfaces:
            if item.is_applied():
                 task2 = ConfigTask(ms, ms.network_interfaces,
                          'ms upgrade network_interfaces task',
                          'ms::network_interfaces', 'up_ms_net')
                 tasks.append(task2)
        if ms.storage_profile.is_applied():
                task3 = ConfigTask(ms, ms.storage_profile,'ms upgrade Storage profile task',
                          'ms::storage_profile','up_ms_storage')
                tasks.append(task3)
        for item in ms.os:
            if item.is_applied():
                task4 = ConfigTask(ms, ms.os,'ms upgrade os task',
                          'ms::os','up_ms_os')
                tasks.append(task4)
        if ms.system.is_applied():
                task5 = ConfigTask(ms, ms.system,'ms upgrade system task',
                          'ms::system','up_ms_system')
                tasks.append(task5)
        for item in ms.configs:
            if item.is_applied():
                task6 = ConfigTask(ms, ms.configs,'ms upgrade configs task',
                          'ms::configs','up_ms_config')
                tasks.append(task6)
        for item in ms.items:
            if item.is_applied():
                task7 = ConfigTask(ms, ms.items,'ms upgrade items task',
                          'ms::items','up_ms_item')
                tasks.append(task7)
        for item in ms.services:
            if item.is_applied():
                task8 = ConfigTask(ms, ms.services,'ms upgrade services task',
                          'ms::services','up_ms_service')
                tasks.append(task8)
        for item in ms.routes:
            if item.is_applied():
                task9 = ConfigTask(ms, ms.routes,'ms upgrade routes task',
                          'ms::routes','up_ms_route')
                tasks.append(task9)

        for node in sorted(plugin_api_context.query("node")):
            for item in node.file_systems:
                if item.is_applied():
                    task14 = ConfigTask(node, node.file_systems, 'node upgrade file_systems task', 'node::file_systems', 'up_node_file')
                    tasks.append(task14)
            for item in node.network_interfaces:
                if item.is_applied():
                    task15 = ConfigTask(node, node.network_interfaces, 'node upgrade network_interfaces task','node::network_interfaces', 'up_node_net')
                    tasks.append(task15)
            if node.storage_profile.is_applied():
                    task16 = ConfigTask(node, node.storage_profile, "node upgrade Storage_profile task", "node::storage_profile", 'up_node_storage')
                    tasks.append(task16)
            for item in  node.os:
                if item.is_applied():
                    task17 = ConfigTask(node, node.os, "node upgrade os task", "node::os", "up_node_os")
                    tasks.append(task17)
            if node.system.is_applied():
                    task18 = ConfigTask(node, node.system, 'node upgrade system task','node::system', 'up_node_system')
                    tasks.append(task18)
            for item in node.items:
                if item.is_applied():
                    task19 = ConfigTask(node, node.items, 'node upgrade items task','node::items', 'up_node_item')
                    tasks.append(task19)
            for item in node.services:
                if item.is_applied():
                    task20 = ConfigTask(node, node.services, 'node upgrade services task','node::services', 'up_node_service')
                    tasks.append(task20)
            for item in node.configs:
                if item.is_applied():
                    task21 = ConfigTask(node, node.configs, 'node upgrade configs task','node::configs', 'up_node_config')
                    tasks.append(task21)
            for item in node.routes:
                if item.is_applied():
                    task22 = ConfigTask(node, node.routes, 'node upgrade routes task','node::routes', 'up_node_route')
                    tasks.append(task22)
        return tasks
