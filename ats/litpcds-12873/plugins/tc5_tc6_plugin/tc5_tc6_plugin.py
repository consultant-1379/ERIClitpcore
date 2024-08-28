from litp.core.plugin import Plugin
from litp.core.task import ConfigTask, CallbackTask

class Litpcds12873Plugin(Plugin):
    """
    Test plugin for LITPCDS-12873
    Required Callback task is not returned and also requires 2 other tasks
    (one returned and one not)
    """

    def create_configuration(self, api):
        return self.create_configuration_ms(api) + \
               self.create_configuration_node(api)

    def create_configuration_ms(self, api):
        tasks = []
        ms = api.query('ms')[0]

        for item in ms.routes:
            if item.item_id == 'route_a_tc5' and item.is_initial():
                task4_ms = ConfigTask(ms, item, 'ms routes_a task',
                         'ms::routes_a', 'id_ms_route_a')
                tasks.append(task4_ms)
            if item.item_id == 'route_b_tc5' and item.is_initial():
                task5_ms = ConfigTask(ms, item, 'ms routes_b task',
                         'ms::routes_b', 'id_ms_route_b')
                # Do not return task5_ms
                # tasks.append(task5_ms)

        for item in ms.file_systems:
            if item.item_id == 'file_system_tc5' and item.is_initial():
                 task3_ms = ConfigTask(ms, item, 'ms file_systems task',
                          'ms::file_systems', 'id_ms_file')
                 tasks.append(task3_ms)

        for item in ms.configs:
            if item.item_id == 'config_tc5' and item.is_initial():
                # Callback task
                task2_ms = CallbackTask(item, 'ms Callback task', Litpcds12873Plugin._cb)
                # Intentionally do not return task2_ms
                # tasks.append(task2_ms)
                # Dependency on 2 others tasks, one returned and one not
                task2_ms.requires.add(task4_ms)
                task2_ms.requires.add(task5_ms)

        for item in ms.items:
            if item.item_id == 'item_tc5' and item.is_initial():
                task1_ms = ConfigTask(ms, item,'ms items task',
                          'ms::items','id_ms_item')
                # required Callback task will not be returned by plugin
                task1_ms.requires.add(task2_ms)
                tasks.append(task1_ms)
        return tasks

    def create_configuration_node(self, api):
        tasks = []
        for node in api.query('node'):
            for item in node.routes:
                if item.item_id == 'route_a_tc6' and item.is_initial():
                    task4_node = ConfigTask(node, item, 'node routes_a task',
                             'node::routes_a', 'id_node_route_a')
                    tasks.append(task4_node)
                if item.item_id == 'route_b_tc6' and item.is_initial():
                    task5_node = ConfigTask(node, item, 'node routes_b task',
                             'node::routes_b', 'id_node_route_b')
                    # Do not return task5_node
                    # tasks.append(task5_node)
            for item in node.file_systems:
                if item.item_id == 'file_system_tc6' and item.is_initial():
                    task3_node = ConfigTask(node, item, 'node file_systems task',
                               'node::file_systems', 'id_node_file')
                    tasks.append(task3_node)

            for item in node.configs:
                if item.item_id == 'config_tc6' and item.is_initial():
                    # Callback task
                    task2_node = CallbackTask(item, 'node Callback task', Litpcds12873Plugin._cb)
                    # Intentionally do not return task2_node
                    # tasks.append(task2_node)
                    # Dependency on 2 others tasks, one returned and one not
                    task2_node.requires.add(task4_node)
                    task2_node.requires.add(task5_node)

            for item in node.items:
                if item.item_id == 'item_tc6' and item.is_initial():
                    task1_node = ConfigTask(node, item, 'node items task',
                               'node::items', 'id_node_item')
                    # required task will not be returned by plugin
                    task1_node.requires.add(task2_node)
                    tasks.append(task1_node)
        return tasks

    def _cb(self, api):
        pass
