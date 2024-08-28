from litp.core.plugin import Plugin
from litp.core.task import ConfigTask
from litp.core.task import CallbackTask
from litp.core.future_property_value import FuturePropertyValue


class FuturePropertyPlugin(Plugin):
    def __init__(self, *args, **kwargs):
        super(FuturePropertyPlugin, self).__init__(*args, **kwargs)

    def create_configuration(self, api):
        tasks = []

        for node in sorted(api.query("node")):
            for test_item in node.query("test_item"):
                future_property_value = FuturePropertyValue(
                        test_item, "version")
                task1 = CallbackTask(node,
                        "Callback - update FuturePropertyValue",
                                self.cb_update_property)
                task2 = ConfigTask(node, test_item, "standalone ConfigTask",
                            "package", test_item.name,
                            version=future_property_value)
                if self.is_callback_disabled(api):
                    tasks.extend([task2])
                else:
                    task2.requires.add(task1)
                    tasks.extend([task1, task2])

        if self.task_trigger_found(api):
            for node in sorted(api.query("node")):
                for test_item in node.query("test_item"):
                    future_property_value = FuturePropertyValue(
                            test_item, "version")
                    task3 = CallbackTask(node,
                                "Callback - update FuturePropertyValue again",
                                self.cb_update_property_again)
                    task4 = ConfigTask(node,
                                test_item,
                                "standalone ConfigTask no. 2",
                                "package", test_item.name + "_another",
                                version=future_property_value)

                    task3.requires.add(task2)
                    task4.requires.add(task3)
                    tasks.extend([task3, task4])

        # Test FuturePropertyValue views below.
        # Test runtime ViewError
        if self.error_trigger_found(api):
            for node in sorted(api.query("node")):
                for test_item in node.query("test_item"):
                    future_property_value = FuturePropertyValue(
                            test_item, "version")
                    task3 = CallbackTask(node,
                                    "Callback - update FuturePropertyValue " \
                                            "to trigger an error",
                                    self.cb_update_to_get_error)

                    future_property_value = \
                            FuturePropertyValue(
                                    test_item, "viewerror_on_runtime_view")
                    task_node_view = ConfigTask(node, test_item,
                            "Should get a runtime ViewError",
                            "package", "call_id_E",
                            viewerror_on_runtime_view=future_property_value)


                    task3.requires.add(task2)
                    tasks.extend([task3])

                    task_node_view.requires.add(task3)
                    tasks.extend([task_node_view])

        # Test if a view gets evaluated only once.
        if self.view_trigger_found(api):
            for node in sorted(api.query("node")):
                for test_item in node.query("test_item"):
                    future_property_value = \
                            FuturePropertyValue(
                                        test_item, "test_item_view")
                    task_node_view = ConfigTask(node,
                                        test_item, "Node View Task",
                                        "package", "call_id_A",
                                        test_item_view=future_property_value)
                    if test_item.evaluate_once == "false":
                        task_node_view.requires.add(task2)
                    tasks.extend([task_node_view])

        # Test FuturePropertyValue ViewError raised.
        if self.view_error_trigger_found(api):
            for node in sorted(api.query("node")):
                for test_item in node.query("test_item"):
                    future_property_value = \
                            FuturePropertyValue(test_item, "viewerror_view")
                    task_node_view = ConfigTask(node, test_item,
                                        "Should raise ViewError",
                                        "package", "call_id_B",
                                        viewerror_view=future_property_value)
                    task_node_view.requires.add(task2)
                    tasks.extend([task_node_view])

        # Test FuturePropertyValue Exception raised
        if self.view_exception_trigger_found(api):
            for node in sorted(api.query("node")):
                for test_item in node.query("test_item"):
                    future_property_value = \
                            FuturePropertyValue(test_item, "exception_view")
                    task_node_view = ConfigTask(node, test_item,
                                        "Should raise ViewError",
                                        "package", "call_id_C",
                                        exception_view=future_property_value)
                    task_node_view.requires.add(task2)
                    tasks.extend([task_node_view])
        return tasks

    def is_callback_disabled(self, api):
        for test_item in api.query("test_item"):
            if test_item.name == "disable_callback":
                return True
        return False

    def task_trigger_found(self, api):
        for test_item in api.query("test_item"):
            if test_item.name == "task_trigger":
                return True
        return False

    def error_trigger_found(self, api):
        for test_item in api.query("test_item"):
            if test_item.name == "expect_view_error":
                return True
        return False

    def view_trigger_found(self, api):
        for test_item in api.query("test_item"):
            if test_item.name == "view_trigger":
                return True
        return False

    def view_error_trigger_found(self, api):
        for test_item in api.query("test_item"):
            if test_item.name == "view_error_trigger":
                return True
        return False

    def view_exception_trigger_found(self, api):
        for test_item in api.query("test_item"):
            if test_item.name == "view_exception_trigger":
                return True
        return False

    def cb_update_property(self, api):
        node = api.query('node')[0]
        for test_item in node.query("test_item"):
            test_item.version = "Y.Y.Y"

    def cb_update_property_again(self, api):
        node = api.query('node')[0]
        for test_item in node.query("test_item"):
            test_item.version = "Z.Z.Z"

    def cb_update_to_get_error(self, api):
        node = api.query('node')[0]
        for test_item in node.query("test_item"):
            test_item.viewerror_on_runtime = "true"

