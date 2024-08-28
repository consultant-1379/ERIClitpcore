from litp.core.plugin import Plugin
from litp.core.task import CallbackTask
from litp.core.exceptions import CallbackExecutionException


class DummyPlugin11190(Plugin):

    def _cb_fail(self, *args, **kwargs):
        raise CallbackExecutionException("Oh no!")

    def create_configuration(self, api):
        item = api.query_by_vpath('/deployments/local/clusters/cluster1/nodes/node2')
        task = CallbackTask(item, 'LITPCDS-11190 failing CallbackTask', self._cb_fail)
        return [task]
