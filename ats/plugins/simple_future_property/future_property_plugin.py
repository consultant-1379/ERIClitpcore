from litp.core.plugin import Plugin
from litp.core.task import ConfigTask
from litp.core.task import CallbackTask
from litp.core.future_property_value import FuturePropertyValue


class FuturePropertyPlugin(Plugin):
    def __init__(self, *args, **kwargs):
        super(FuturePropertyPlugin, self).__init__(*args, **kwargs)

    def create_configuration(self, api):
        tasks = []

        for node in sorted(api.query("node") + api.query("ms")):
            for test_item in node.query("test_item"):
                future_property_value = FuturePropertyValue(
                        test_item, "version")
                task = ConfigTask(node, test_item, "Check View",
                            "package", test_item.name,
                            version=future_property_value)
                tasks.append(task)
        return tasks
