from litp.core.plugin import Plugin
from litp.core.task import CallbackTask, ConfigTask
from litp.plan_types.deployment_plan import deployment_plan_tags
from litp.core.litp_logging import LitpLogger
from itertools import chain
log = LitpLogger()

class FailurePlugin(Plugin):

    def _ms_cb(self, api):
        pass

    def _post_cluster_cb(self, api):
        pass

    def create_configuration(self, api):
        tasks = []
        for item in api.query("litpcds-107214b"):
            ms_task = CallbackTask(item, "MS task on %s" % item.item_id, self._ms_cb)
            ms_task.tag_name = deployment_plan_tags.MS_TAG
            queryItems=chain.from_iterable(node.query('litpcds-107214a') for node in api.query('node'))
            ms_task.requires |= set(queryItems)
        for cluster in api.query("cluster-base"):
            post_cluster_task = CallbackTask(cluster, "Pre-node task on %s" % cluster.item_id, self._post_cluster_cb)
            post_cluster_task.tag_name = deployment_plan_tags.POST_CLUSTER_TAG
            for cluster_node in cluster.query("node"):
                for node_item in cluster_node.query("litpcds-107214a"):
                    tasks.append(ConfigTask(
                        cluster_node,
                        node_item,
                        'Node task for %s' % cluster_node.hostname,
                        "call_id_{0}".format(node_item.prop),
                        'bar_%s' % cluster_node.hostname[-1]
                    ))

            tasks.extend([post_cluster_task])
        tasks.append(ms_task)
        return tasks
