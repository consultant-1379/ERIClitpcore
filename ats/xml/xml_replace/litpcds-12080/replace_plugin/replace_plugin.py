from litp.core.plugin import Plugin
from litp.core.task import ConfigTask
from litp.core.task import CallbackTask
from litp.core.task import RemoteExecutionTask


class DummyPlugin(Plugin):

    def __init__(self, *args, **kwargs):
        super(DummyPlugin, self).__init__(*args, **kwargs)

    def create_configuration(self, api):
        tasks = []
        ms = api.query_by_vpath('/ms')
        item_list = api.query('dummy_extension')
        for index, item in enumerate(item_list):
            prefix = "Update"
            if item.is_initial():
                prefix = "Create"
            elif item.is_for_removal():
                prefix = "Remove"
            elif item.is_applied():
                continue
            tasks.append(
                ConfigTask(
                    ms, item, '%s plugin task for item %s' %(prefix, index),
                    'DummyPlugin.task',
                    'DummyPlugin.%s_task_%s' %(str.lower(prefix),index))
                )
        return tasks
