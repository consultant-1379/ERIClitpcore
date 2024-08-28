from litp.core.plugin import Plugin
from litp.core.task import CallbackTask, ConfigTask

class UpdateUpPlugPropertyPlugin(Plugin):
    def __init__(self, *args, **kwargs):
        super(UpdateUpPlugPropertyPlugin, self).__init__(*args, **kwargs)

    def cb_update_property(self, callback_api, *args):
        # Break regex validation (cmw or vcs)
        callback_api.query("cluster")[0].ha_manager="1._qBA-"

    def create_configuration(self, plugin_api_context):
        cluster = plugin_api_context.query("cluster")[0]
        return [ CallbackTask(cluster, 'Callback', self.cb_update_property)]
