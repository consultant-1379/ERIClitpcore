from litp.core.plugin import Plugin
from litp.core.execution_manager import ConfigTask
from litp.core.execution_manager import RemoteExecutionTask

class TestPlugin(Plugin):

    def validate_model(self, plugid_api_context):
        return []

    def create_configuration(self, plugid_api_context):
        tasks = []
        node = plugid_api_context.query("node")[0]
        for item in node.file_systems:
            if item.is_initial():
                task14 = ConfigTask(node, node.file_systems, 'node install file_systems task', 'node::file_systems', 'id_node_file')
                tasks.append(task14)
        for item in node.network_interfaces:
            if item.is_initial():
                task15 = ConfigTask(node, node.network_interfaces, 'node install network_interfaces task','node::network_interfaces', 'id_node_net')
                tasks.append(task15)
        if node.storage_profile.is_initial():
                task16 = ConfigTask(node, node.storage_profile, "node install Storage_profile task", "node::storage_profile", 'id_node_storage')
                tasks.append(task16)
        if node.os.is_initial():
                task17 = ConfigTask(node, node.os, "node install os task", "node::os", "id_node_os")
                tasks.append(task17)
        if node.system.is_initial():
                task18 = ConfigTask(node, node.system, 'node install system task','node::system', 'id_node_system')
                tasks.append(task18)
        for item in node.items:
            if item.is_initial():
                task19 = ConfigTask(node, node.items, 'node install items task','node::items', 'id_node_item')
                tasks.append(task19)
        for item in node.services:
            if item.is_initial():
                task20 = ConfigTask(node, node.services, 'node install services task','node::services', 'id_node_service')
                tasks.append(task20)
        for item in node.configs:
            if item.is_initial():
                task21 = ConfigTask(node, node.configs, 'node install configs task','node::configs', 'id_node_config')
                tasks.append(task21)
        for item in node.routes:
            if item.is_initial():
                task22 = ConfigTask(node, node.routes, 'node install routes task','node::routes', 'id_node_route')
                tasks.append(task22)
        return tasks

    def create_lock_tasks(self, plugid_api_context, node):
        nodes = sorted(plugid_api_context.query("node"))[0]
        return (
            RemoteExecutionTask([node], nodes, "Lock node %s" % node.item_id, "lock_unlock", "lock"),
            RemoteExecutionTask([node], nodes, "Unlock node %s" % node.item_id, "lock_unlock", "unlock"),
        )
