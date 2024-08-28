from litp.core.plugin import Plugin
from litp.core.task import CallbackTask

from litp.core.litp_logging import LitpLogger
log = LitpLogger()


class Test14Plugin(Plugin):
    def callback(self, api, item_name):
        for item in api.query("story2783", name=item_name):
            item.plugin_only = str(int(item.plugin_only) + 1)

    def create_configuration(self, api):
        tasks = []
        for item in api.query("story2783"):
            tasks.extend([CallbackTask(item, "", self.callback,
                                       item.name)])

        return tasks
