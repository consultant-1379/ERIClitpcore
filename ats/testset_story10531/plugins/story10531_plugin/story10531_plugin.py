from litp.core.plugin import Plugin
from litp.core.task import ConfigTask
from litp.plan_types.deployment_plan import deployment_plan_tags
from litp.core.task import OrderedTaskList

class Story10531Plugin(Plugin):
    """
    Test plugin for LITPCDS-10531
    This plugin creates tagged tasks based on the default 'deployment_plan_tags'
    MS_TAG, BOOT_TAG, NODE_TAG and CLUSTER_TAG
    Each test case uses its own 'create_configuration'
    'create_configuration_tc1' creates tasks for valid tags
    'create_configuration_tc2' and 'create_configuration_tc4' create
    tagged tasks with added dependencies for
     - Direct task-to-task dependency within same plugin
     - Config task Dependency using call type/id
     - Query item dependency
    'create_configuration_tc3' returns a task with an invalid tag
    'create_configuration_tc5' uses a different task's tag for creation and removal
    'create_configuration_tc6' creates queryItem dependency for tasks in different groups
    """

    def create_configuration(self, api):
        return self.create_configuration_tc1(api) + \
               self.create_configuration_tc2(api) + \
               self.create_configuration_tc3(api) + \
               self.create_configuration_tc4(api) + \
               self.create_configuration_tc5(api) + \
               self.create_configuration_tc6(api) + \
               self.create_configuration_tc7(api) + \
               self.create_configuration_tc8(api)

    def create_configuration_tc1(self, api):
        tasks = []
        for node in api.query('node'):
            for item in node.query('foo1', is_initial=True):
                tasks.append(ConfigTask(
                    node, item,
                    'tagged as MS',
                    'res_ms', 'apache-package',
                    tag_name=deployment_plan_tags.MS_TAG))
                tasks.append(ConfigTask(
                    node, item,
                    'tagged as BOOT',
                    'res_boot_1', 'apache.conf',
                    tag_name=deployment_plan_tags.BOOT_TAG))
                tasks.append(ConfigTask(
                    node, item,
                    'tagged as BOOT',
                    'res_boot_2', 'httpd.conf',
                    tag_name=deployment_plan_tags.BOOT_TAG))
                tasks.append(ConfigTask(
                    node, item,
                    'tagged as CLUSTER',
                    'res_cluster', 'httpd_2',
                    tag_name=deployment_plan_tags.CLUSTER_TAG))
                tasks.append(ConfigTask(
                    node, item,
                    'tagged as NODE',
                    'res_node', 'httpd_1',
                    tag_name=deployment_plan_tags.NODE_TAG))
        return tasks

    def create_configuration_tc2(self, api):
        tasks = []
        for node in api.query('node'):
            for item in node.query('foo2_1', is_initial=True):
                task1=ConfigTask(
                    node, item,
                    'Plugin1, task1 tagged as MS',
                    'tc2_res_1_ms', 'tc2_res_1_ms_title',
                    tag_name=deployment_plan_tags.MS_TAG)
                task2=ConfigTask(
                    node, item,
                    'Plugin1 tasks2 tagged as BOOT',
                    'tc2_res_2_boot', 'tc2_res_2_boot_title',
                    tag_name=deployment_plan_tags.BOOT_TAG)
                task3=ConfigTask(
                    node, item,
                    'Plugin1 task3 tagged as CLUSTER, requires '
                        'queryItem item4 (Callback task32 and Config task33)',
                    'tc2_res_3_cluster', 'tc2_res_3_cluster_title',
                    tag_name=deployment_plan_tags.CLUSTER_TAG)
                task4=ConfigTask(
                    node, item,
                    'Plugin1 tasks4 tagged as NODE, requires '
                        'task5 (direct task-to-task dependency)',
                    'tc2_res_4_node', 'tc2_res_4_node_title',
                    tag_name=deployment_plan_tags.NODE_TAG)
                task5=ConfigTask(
                    node, item,
                    'Plugin1 tasks5 tagged as NODE, requires '
                        'task24 (config task dependency using call type/id)',
                    'tc2_res_5_node', 'tc2_res_5_node_title',
                    tag_name=deployment_plan_tags.NODE_TAG)

                # Direct task-to-task dependency within same plugin
                # Node task4 requires node task5
                task4.requires.add(task5)

                # Config task Dependency between tasks generated
                # by different plugins, same Group
                # Node task5 requires node task24 from other plugin
                # by specifying the call type and call id of task24
                task5.requires.add(('pg2_res_24_node','pg2_res_24_node_title'))

                # Query item dependency
                # Cluster task3 requires model item foo2_3
                queryItem=node.query('foo2_3')[0]
                task3.requires.add(queryItem)

                tasks.extend([task5, task4, task3, task2, task1])

        return tasks

    def create_configuration_tc3(self, api):
        tasks = []
        for node in api.query('node'):
            for item in node.query('foo3', is_initial=True):
                tasks.append(ConfigTask(
                    node, item,
                    'tagged as MS',
                    'res_ms', 'apache-package',
                    tag_name=deployment_plan_tags.MS_TAG))
                tasks.append(ConfigTask(
                    node, item,
                    'tagged as BOOT',
                    'res_boot_1', 'apache.conf',
                    tag_name=deployment_plan_tags.BOOT_TAG))
                tasks.append(ConfigTask(
                    node, item,
                    'tagged as CLUSTER',
                    'res_cluster', 'httpd_2',
                    tag_name=deployment_plan_tags.CLUSTER_TAG))
                tasks.append(ConfigTask(
                    node, item,
                    'tagged as NODE',
                    'res_node', 'httpd_1',
                    tag_name=deployment_plan_tags.NODE_TAG))
                tasks.append(ConfigTask(
                    node, item,
                    'tagged as invalid_tag_name',
                    'res_invalid_tag', '.conf',
                    tag_name="invalid_tag_name"))
        return tasks

    def create_configuration_tc4(self, api):
        tasks = []
        for node in api.query('node'):
            for item in node.query('foo4', is_initial=True):
                if item.task_dependency_type == 't2t':
                    # Direct task-to-task dependency within same plugin,
                    # but different group.
                    task_boot_2 = ConfigTask(
                        node, item,
                        'tagged as BOOT',
                        'tc4_res_boot_2', 'tc4_res_boot_2_title',
                        tag_name=deployment_plan_tags.BOOT_TAG)
                    task_node = ConfigTask(
                        node, item,
                        'tagged as NODE',
                        'tc4_res_node', 'tc4_res_node_title',
                        tag_name=deployment_plan_tags.NODE_TAG)
                    task_node.requires.add(task_boot_2)
                    tasks.extend([task_boot_2, task_node])
                elif item.task_dependency_type == 'call_type_id':
                    # Config task Dependency between tasks generated
                    # by different plugins, from different group
                    task_cluster = ConfigTask(
                        node, item,
                        'tagged as CLUSTER',
                        'tc4_res_cluster', 'tc4_res_cluster_title',
                        tag_name=deployment_plan_tags.CLUSTER_TAG)
                    task_cluster.requires.add(
                            ('tc4_res_ms', 'tc4_res_ms_title'))
                    tasks.append(task_cluster)
                elif item.task_dependency_type == 'query_item' and \
                     item.name == 'item3':
                    # Query item dependency
                    # tasks tagged as node and associated with different nodes
                    task_node = ConfigTask(
                        node, item,
                        'tagged as NODE',
                        'tc4_res_node_2', 'tc4_res_node_title_2',
                        tag_name=deployment_plan_tags.NODE_TAG)
                    queryItem = api.query('node', item_id='node2')[0].query('foo4', item_id='item4')[0]
                    task_node.requires.add(queryItem)
                    tasks.append(task_node)
                elif item.task_dependency_type == 'query_item' and \
                     item.name == 'item5':
                    # Query item dependency
                    # with invalid group order dependency
                    # task from ms group depends on task from boot
                    task_ms = ConfigTask(
                        node, item,
                        'tagged as MS',
                        'tc4_res_ms_2', 'tc4_res_ms_title_2',
                        tag_name=deployment_plan_tags.MS_TAG)
                    queryItem=node.query('foo4' , item_id='item6')[0]
                    task_ms.requires.add(queryItem)
                    tasks.append(task_ms)
                elif item.task_dependency_type == 'query_item' and \
                     item.name == 'item7':
                    # Query item dependency
                    # with tasks tagged as node
                    # vpath associated with node and ms
                    task_node = ConfigTask(
                        node, item,
                        'tagged as NODE',
                        'tc4_res_node_2', 'tc4_res_node_title_2',
                        tag_name=deployment_plan_tags.NODE_TAG)
                    queryItem=api.query('ms')[0].query('foo4' , item_id='item8')[0]
                    task_node.requires.add(queryItem)
                    tasks.append(task_node)

        return tasks

    def create_configuration_tc5(self, api):
        tasks = []
        for node in api.query('node'):
            for item in node.query('foo5'):
                if item.is_initial():
                    tasks.append(ConfigTask(
                        node, item,
                        'Configuration task for {0} tagged as MS'.format(item.name),
                        'file', 'apache.conf',
                        ensure='present',
                        tag_name=deployment_plan_tags.MS_TAG))
                    tasks.append(ConfigTask(
                        node, item,
                        'Configuration task for {0} tagged as MS'.format(item.name),
                        'package', 'package_1',
                        ensure='present',
                        tag_name=deployment_plan_tags.MS_TAG))
                    tasks.append(ConfigTask(
                        node, item,
                        'Configuration task for {0} tagged as BOOT'.format(item.name),
                        'service', 'apache',
                        ensure='present',
                        tag_name=deployment_plan_tags.BOOT_TAG))
                    tasks.append(ConfigTask(
                        node, item,
                        'Configuration task for {0} tagged as NODE'.format(item.name),
                        'file', 'httpd.conf',
                        ensure='present',
                        tag_name=deployment_plan_tags.NODE_TAG))
                    tasks.append(ConfigTask(
                        node, item,
                        'Configuration task for {0} tagged as CLUSTER'.format(item.name),
                        'package', 'package_2',
                        ensure='present',
                        tag_name=deployment_plan_tags.CLUSTER_TAG))
                elif item.is_for_removal():
                    tasks.append(ConfigTask(
                        node, item,
                        'Deconfiguration task for {0} tagged as NODE'.format(item.name),
                        'file', 'apache.conf',
                        ensure='absent',
                        tag_name=deployment_plan_tags.NODE_TAG))
                    tasks.append(ConfigTask(
                        node, item,
                        'Deconfiguration task for {0} tagged as MS'.format(item.name),
                        'package', 'package_1',
                        tag_name=deployment_plan_tags.MS_TAG))
                    tasks.append(ConfigTask(
                        node, item,
                        'Deconfiguration task for {0} tagged as BOOT'.format(item.name),
                        'service', 'apache',
                        ensure='absent',
                        tag_name=deployment_plan_tags.BOOT_TAG))
                    tasks.append(ConfigTask(
                        node, item,
                        'Deconfiguration task for {0} tagged as NODE'.format(item.name),
                        'file', 'httpd.conf',
                        ensure='absent',
                        tag_name=deployment_plan_tags.NODE_TAG))
                    tasks.append(ConfigTask(
                        node, item,
                        'Deconfiguration task for {0} tagged as CLUSTER'.format(item.name),
                        'package', 'package_2',
                        ensure='absent',
                        tag_name=deployment_plan_tags.CLUSTER_TAG))

        return tasks

    def create_configuration_tc6(self, api):
        tasks = []
        for node in api.query('node'):
            for item in node.query('foo6', is_initial=True):
                if item.task_dependency_type == 'query_item' and \
                     item.name == 'item1':
                    # Query item dependency
                    # with valid group order dependency
                    # task from node group depends on tasks from boot group
                    task_node = ConfigTask(
                        node, item,
                        'tagged as NODE',
                        'tc6_res_node', 'tc6_res_node_title',
                        tag_name=deployment_plan_tags.NODE_TAG)
                    queryItem=node.query('foo6' , item_id='item2')[0]
                    task_node.requires.add(queryItem)
                    tasks.append(task_node)

        return tasks

    def create_configuration_tc7(self, api):
        tasks = []
        for node in api.query('node'):
            for item in node.query('foo7', is_initial=True):
                ordered_tasks = []
                ordered_tasks.append(ConfigTask(
                    node, item,
                    'First ordered task - tagged as NODE',
                    'res_1_node', 'res_1_node_title',
                    tag_name=deployment_plan_tags.NODE_TAG))
                ordered_tasks.append(ConfigTask(
                    node, item,
                    'Second ordered task - tagged as NODE',
                    'res_2_node', 'res_2_node_title',
                    tag_name=deployment_plan_tags.NODE_TAG))
                ordered_tasks.append(ConfigTask(
                    node, item,
                    'Third ordered task - tagged as NODE',
                    'res_3_node', 'res_3_node_title',
                    tag_name=deployment_plan_tags.NODE_TAG))
                tasks.append(OrderedTaskList(item, ordered_tasks))

        return tasks

    def create_configuration_tc8(self, api):
        tasks = []
        for node in api.query('node'):
            for item in node.query('foo8', is_initial=True):
                ordered_tasks = []
                ordered_tasks.append(ConfigTask(
                    node, item,
                    'tagged as MS',
                    'res_ms', 'apache-package',
                    tag_name=deployment_plan_tags.MS_TAG))
                ordered_tasks.append(ConfigTask(
                    node, item,
                    'tagged as BOOT',
                    'res_boot', 'apache.conf',
                    tag_name=deployment_plan_tags.BOOT_TAG))
                ordered_tasks.append(ConfigTask(
                    node, item,
                    'tagged as NODE',
                    'res_node', 'httpd_1',
                    tag_name=deployment_plan_tags.NODE_TAG))
                ordered_tasks.append(ConfigTask(
                    node, item,
                    'tagged as CLUSTER',
                    'res_cluster', 'httpd_2',
                    tag_name=deployment_plan_tags.CLUSTER_TAG))
                tasks.append(OrderedTaskList(item, ordered_tasks))

        return tasks
