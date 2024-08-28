from litp.core.plugin import Plugin
from litp.core.task import ConfigTask
from litp.core.task import CallbackTask
from litp.core.task import OrderedTaskList

class UpdatePropertyPlugin(Plugin):
    def __init__(self, *args, **kwargs):
        super(UpdatePropertyPlugin, self).__init__(*args, **kwargs)

    def create_configuration(self, api):
        tasks = []

        for node in sorted(api.query("node")):
            for test_item in node.query("test_item"):
                task1 = CallbackTask(node, "Callback - update property",
                                self.cb_update_property)

                task2 = CallbackTask(node, "Callback - do nothing",
                                self.cb_do_nothing)

                task3 = CallbackTask(node, "Callback - update property again",
                                self.cb_update_property_again)

                ordered_tasks = OrderedTaskList(test_item,
                                                [task1, task2, task3])
                tasks.append(ordered_tasks)

        return tasks

    def cb_do_nothing(self, api):
        pass

    def cb_update_property(self, api):
        node = api.query('node')[0]
        for test_item in node.query("test_item"):
            test_item.version = "Y.Y.Y"

    def cb_update_property_again(self, api):
        node = api.query('node')[0]
        for test_item in node.query("test_item"):
            test_item.version = "Z.Z.Z"
