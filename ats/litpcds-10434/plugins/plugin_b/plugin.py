from litp.core.plugin import Plugin
from litp.core.task import ConfigTask


class PluginA(Plugin):

    def create_configuration(self, api):
        item = api.query_by_vpath('/deployments/local/clusters/cluster1/nodes/node2')
        task = ConfigTask(item, item, 'PluginA task 2', 'PluginA.task_2', '2')
        return [task]
