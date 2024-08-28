from litp.core.plugin import Plugin
from litp.core.task import ConfigTask


class ClusterOrderingPlugin(Plugin):
    def create_configuration(self, api):
        tasks = []
        deployment = api.query_by_vpath('/deployments/local')
        node = api.query_by_vpath(
            '/deployments/local/clusters/cluster2/nodes/node2')
        ordered_clusters = ','.join(
                [item.item_id for item in deployment.ordered_clusters])
        task = ConfigTask(
                node, deployment, 'description', ordered_clusters, 'call_id')
        tasks.append(task)
        return tasks
