from litp.core.plugin import Plugin
from litp.core.execution_manager import CallbackTask


class Dummy12017Plugin(Plugin):

    def update_model(self, plugin_api_context):
        item = plugin_api_context.query_by_vpath(
                "/deployments/local/clusters/cluster1/nodes/node1/items/foo")
        if item:
            # Update item that previously failed removal
            item.updatable_prop = 'something'
