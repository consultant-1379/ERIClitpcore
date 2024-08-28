from litp.core.plugin import Plugin
from litp.core.task import ConfigTask, CallbackTask, RemoteExecutionTask
from litp.plan_types.deployment_plan import deployment_plan_tags


class Story10531Plugin2(Plugin):
    """
    Second test plugin for LITPCDS-10531
    This plugin creates tasks to be used in tagged task dependencies
    with other tasks defined in the first plugin.
    This plugin creates tagged tasks based on the default 'deployment_plan_tags'
    MS_TAG, BOOT_TAG, NODE_TAG and CLUSTER_TAG
    It also creates lock tasks.
    Task24 for item type 'foo2_2' is used in the 'config task' dependency
    case in test case 2.
    Task32 and task33 for item_type foo2_3 are used in the 'queryItem'
    dependency in test case 2.
    Tasks for item type foo4 are used for test case 4 dependencies.
    """

    def _mock_function(self, *args, **kwargs):
        pass

    def create_configuration(self, api):
        tasks = []
        for node in api.query('node'):
            for item in node.query('foo2_2', is_initial=True):
                task21 = ConfigTask(
                    node, item,
                    'Plugin2, task21 tagged as MS',
                    'pg2_res_21_ms', 'pg2_res_21_ms_title',
                    tag_name=deployment_plan_tags.MS_TAG)
                task22 = ConfigTask(
                    node, item,
                    'Plugin2, task22 tagged as BOOT',
                    'pg2_res_22_boot', 'pg2_res_22_ms_title',
                    tag_name=deployment_plan_tags.BOOT_TAG)
                task23 = ConfigTask(
                    node, item,
                    'Plugin2, task23 tagged as CLUSTER',
                    'pg2_res_23_cluster', 'pg2_res_23_cluster_title',
                    tag_name=deployment_plan_tags.CLUSTER_TAG)
                task24 = ConfigTask(
                    node, item,
                    'Plugin2, task24 tagged as NODE',
                    'pg2_res_24_node', 'pg2_res_24_node_title',
                    tag_name=deployment_plan_tags.NODE_TAG)
                tasks.extend([task24, task23, task22, task21])
            for item in node.query('foo2_3', is_initial=True):
                task32 = CallbackTask(
                    item,
                    'Plugin2, CallbackTask task32 tagged as CLUSTER',
                    self._mock_function,
                    tag_name=deployment_plan_tags.CLUSTER_TAG)
                task33 = ConfigTask(
                    node, item,
                    'Plugin2, task33 tagged as CLUSTER, used as queried item',
                    'pg2_res_33_cluster', 'pg2_res_33_cluster_title',
                    tag_name=deployment_plan_tags.CLUSTER_TAG)
                tasks.extend([task33, task32])
            for item in node.query('foo4', is_initial=True):
                if item.task_dependency_type == 'call_type_id':
                    task_ms = ConfigTask(
                        node, item,
                        'tagged as MS',
                        'tc4_res_ms', 'tc4_res_ms_title',
                        tag_name=deployment_plan_tags.MS_TAG)
                    tasks.append(task_ms)
                elif item.task_dependency_type == 'query_item' and \
                     item.name == 'item4':
                    task_node = ConfigTask(
                        node, item,
                        'tagged as NODE',
                        'tc4_res_node', 'tc4_res_node_title',
                        tag_name=deployment_plan_tags.NODE_TAG)
                elif item.task_dependency_type == 'query_item' and \
                     item.name == 'item6':
                    task_boot = ConfigTask(
                        node, item,
                        'tagged as BOOT',
                        'tc4_res_boot', 'tc4_res_boot_title',
                        tag_name=deployment_plan_tags.BOOT_TAG)
                    tasks.append(task_boot)
            for item in node.query('foo6', is_initial=True):
                if item.task_dependency_type == 'query_item' and \
                     item.name == 'item2':
                    task_boot = ConfigTask(
                        node, item,
                        'tagged as BOOT',
                        'tc6_res_boot', 'tc6_res_boot_title',
                        tag_name=deployment_plan_tags.BOOT_TAG)
                    task_cb_boot = CallbackTask(
                        item,
                        'Plugin2, CallbackTask tagged as BOOT',
                        self._mock_function,
                        tag_name=deployment_plan_tags.BOOT_TAG)
                    tasks.extend([task_boot, task_cb_boot])

        for node in api.query('ms'):
            for item in node.query('foo4', is_initial=True):
                if item.task_dependency_type == 'query_item' and \
                   item.name == 'item8':
                    task_node = ConfigTask(
                        node, item,
                        'tagged as NODE',
                        'tc4_res_node', 'tc4_res_node_title',
                        tag_name=deployment_plan_tags.NODE_TAG)
                    tasks.append(task_node)

        return tasks

    def create_lock_tasks(self, api, node):

        ms = api.query("ms")[0]
        return (
            RemoteExecutionTask([node], ms, "Lock node %s" % node.vpath, "lock_unlock", "lock"),
            RemoteExecutionTask([node], ms, "Unlock node %s" % node.vpath, "lock_unlock", "unlock"),
        )
