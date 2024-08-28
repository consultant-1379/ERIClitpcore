from litp.core.plugin import Plugin
from litp.core.task import ConfigTask

class Litpcds12873Plugin(Plugin):
    """
    Test plugin for LITPCDS-12873
    """

    def create_configuration(self, api):
        return self.create_configuration_ms(api) + \
               self.create_configuration_node(api)

    def create_configuration_ms(self, api):
        tasks = []
        ms = api.query('ms')[0]

        for item in ms.file_systems:
            if item.item_id == 'file_system_tc1' and item.is_initial():
                 task3_ms = ConfigTask(ms, item, 'ms file_systems task',
                          'ms::file_systems', 'id_ms_file')
                 tasks.append(task3_ms)

        for item in ms.configs:
            if item.item_id == 'config_tc1' and item.is_initial():
                task2_ms = ConfigTask(ms, item,'ms configs task',
                          'ms::configs','id_ms_config')
                # Intentionally do not return task2_ms
                # tasks.append(task2_ms)

        for item in ms.items:
            if item.item_id == 'item_tc1' and item.is_initial():
                task1_ms = ConfigTask(ms, item,'ms items task',
                          'ms::items','id_ms_item')
                # required task will not be returned by plugin
                task1_ms.requires.add(task2_ms)
                tasks.append(task1_ms)
        return tasks

    def create_configuration_node(self, api):
        tasks = []
        for node in api.query('node'):
            for item in node.file_systems:
                if item.item_id == 'file_system_tc2' and item.is_initial():
                    task3_node = ConfigTask(node, item, 'node file_systems task',
                               'node::file_systems', 'id_node_file')
                    tasks.append(task3_node)

            for item in node.configs:
                if item.item_id == 'config_tc2' and item.is_initial():
                    task2_node = ConfigTask(node, item, 'node configs task',
                               'node::configs', 'id_node_config')
                    # Intentionally do not return task2_node
                    # tasks.append(task2_node)

            for item in node.items:
                if item.item_id == 'item_tc2' and item.is_initial():
                    task1_node = ConfigTask(node, item, 'node items task',
                               'node::items', 'id_node_item')
                    # required task will not be returned by plugin
                    task1_node.requires.add(task2_node)
                    tasks.append(task1_node)
        return tasks
