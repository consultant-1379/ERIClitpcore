from litp.core.plugin import Plugin
from litp.core.task import ConfigTask
from litp.core.task import CallbackTask
from litp.core.exceptions import CallbackExecutionException


class Dummy10127Plugin(Plugin):
    def __init__(self, *args, **kwargs):
        super(Dummy10127Plugin, self).__init__(*args, **kwargs)

    def create_configuration(self, api):
        tasks = []
        item = api.query_by_vpath('/software/profiles/litpcds-10127')
        if item and item.is_updated():
            node = api.query_by_vpath('/deployments/local/clusters/cluster1/nodes/node1')
            task = CallbackTask(item, 'Callback for: %s' % item.get_vpath(), self._cb_fail)
            task.model_items.add(node)
            tasks.append(task)
        return tasks

    def _cb_fail(self, api):
        raise CallbackExecutionException
