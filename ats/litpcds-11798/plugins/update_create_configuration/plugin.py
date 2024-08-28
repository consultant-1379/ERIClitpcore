from litp.core.plugin import Plugin
from litp.core.task import CallbackTask
from litp.core.exceptions import CallbackExecutionException


class DummyPlugin11798(Plugin):

    def _cb_fail(self, api, *args, **kwargs):
        pass

    def create_configuration(self, api):
        # Try to update an item that is in ForRemoval state - should fail
        qitem = api.query_by_vpath(
            "/deployments/local/clusters/cluster1/nodes/node1/items/myitem")
        qitem.updatable = 'update_should_be_disallowed_on_for_removal_item'

        # This should never be executed as the code above is supposed to fail
        item = api.query_by_vpath('/deployments/local/clusters/cluster1/nodes/node1')
        task = CallbackTask(item, 'LITPCDS-11798 should fail', self._cb_fail)
        return [task]
