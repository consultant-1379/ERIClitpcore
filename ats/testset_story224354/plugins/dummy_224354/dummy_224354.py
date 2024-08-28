from litp.core.plugin import Plugin
from litp.core.task import ConfigTask
from litp.core.task import CallbackTask
from litp.plan_types.deployment_plan import deployment_plan_tags


class Dummy224354(Plugin):
    def _post_cluster_cb(self, api):
        pass

    def _cluster_cb(self, api):
        pass

    def _pre_cluster_cb(self, api):
        pass

    def create_configuration(self, api):
        tasks = []

        for cluster in api.query("cluster-base"):
            pre_cluster_task = CallbackTask(cluster, "Pre Cluster tagged task on %s" % cluster.item_id, self._pre_cluster_cb)
            pre_cluster_task.tag_name = deployment_plan_tags.PRE_CLUSTER_TAG

            cluster_task = CallbackTask(cluster, "Cluster tagged task on %s" % cluster.item_id, self._cluster_cb)
            cluster_task.tag_name = deployment_plan_tags.CLUSTER_TAG

            post_cluster_task = CallbackTask(cluster, "Post-cluster tagged task on %s" % cluster.item_id, self._post_cluster_cb)
            post_cluster_task.tag_name = deployment_plan_tags.POST_CLUSTER_TAG

            for cluster_node in cluster.query("node"):
                for node_item in cluster_node.query("litpcds-24354"):
                    tasks.append(ConfigTask(
                        cluster_node,
                        node_item,
                        'Dummy node task for %s' % cluster_node.hostname,
                        'cluster_resource',
                        'resource_title_%s' % node_item.prop,
                    ))
            tasks.extend([pre_cluster_task, cluster_task, post_cluster_task])
        return tasks
