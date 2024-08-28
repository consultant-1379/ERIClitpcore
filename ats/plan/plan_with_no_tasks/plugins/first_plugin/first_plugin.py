from litp.core.plugin import Plugin
from litp.core.task import ConfigTask
from litp.core.task import CallbackTask


class FirstPlugin(Plugin):
    def __init__(self, *args, **kwargs):
        super(FirstPlugin, self).__init__(*args, **kwargs)

    def create_configuration(self, api):
        node = api.query("node")[0]
        return [ConfigTask(node, node, "Test ConfigTask", "dummy_call_type",
                "dummy_call_id", list=['one', 'two'])]
