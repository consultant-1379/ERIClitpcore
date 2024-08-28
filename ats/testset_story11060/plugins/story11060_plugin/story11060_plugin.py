from litp.core.plugin import Plugin
from litp.core.task import CallbackTask, ConfigTask
from litp.plan_types.deployment_plan import deployment_plan_tags


class Story11060Plugin(Plugin):

    def _pre_node_cb(self, api):
        pass

    def _post_node_cb(self, api):
        pass

    def _lock_node(self, api):
        pass

    def _unlock_node(self, api):
        pass

    def create_configuration(self, api):
        tasks = []
        # We want pre-node tasks, regular node tasks, lock/unlock tasks and cluster tasks

        for cluster in api.query("cluster-base"):
            pre_node_task = CallbackTask(cluster, "Pre-node task on %s" % cluster.item_id, self._pre_node_cb)
            pre_node_task.tag_name = deployment_plan_tags.PRE_NODE_CLUSTER_TAG
            for cluster_node in cluster.query("node"):
                for node_item in cluster_node.query("litpcds-11060"):
                    tasks.append(ConfigTask(
                        cluster_node,
                        node_item,
                        'Node task for %s' % cluster_node.hostname,
                        'non_networky_resource',
                        'resource_title_%s' % node_item.prop
                    ))
                for node_nw_item in cluster_node.query("network-interface"):
                    tasks.append(ConfigTask(
                        cluster_node,
                        node_nw_item,
                        'Network task for %s' % cluster_node.hostname,
                        'networky_resource',
                        'resource_title_%s' % node_nw_item.network_name
                    ))
            post_node_task = CallbackTask(cluster, "Post-node task on %s" % cluster.item_id, self._post_node_cb)
            tasks.extend([pre_node_task, post_node_task])
        return tasks

    def create_lock_tasks(self, plugin_api_context, node):
        return (
            CallbackTask(node, "Lock task for %s" % node.hostname, self._lock_node),
            CallbackTask(node, "Unlock task for %s" % node.hostname, self._unlock_node),
        )
