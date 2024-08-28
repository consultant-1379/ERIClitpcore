from litp.core.plugin import Plugin
from litp.core.task import ConfigTask
from litp.core.task import CallbackTask
from litp.core.litp_logging import LitpLogger

log = LitpLogger()


class Test12798Plugin_test_12(Plugin):
    """ plugin for test 13, 25, 26"""
    def create_configuration(self, plugid_api_context):
        tasks = []
        tasks_for_items = ['itemB', 'item1', 'item2', 'item3']
        types = ['parent-b', 'parent', 'child', 'g-child', 'g-g-child']
        desc = "Some Task Description"
        i = 0
        callback = self._pass_callback

        # task for itemB in software
        for node in plugid_api_context.query("software"):
            for node_type in types:
                for node_of_type in node.query(node_type):
                    for item in tasks_for_items:
                        if item in node_of_type.vpath:
                            tasks.append(CallbackTask(node_of_type, desc, callback))

        for node in plugid_api_context.query("ms"):

            for node_type in types:
                for node_of_type in node.query(node_type):
                    for item in tasks_for_items:
                        if node_of_type.is_initial() and item in node_of_type.vpath:
                            tasks.append(ConfigTask(node, node_of_type, desc, "task_{0}".format(node_of_type.name),
                                                    "task_{0}".format(str(i)))
                                         )
                            i += 1

        for node in plugid_api_context.query("node"):
            for node_type in types:
                for node_of_type in node.query(node_type):
                    for item in tasks_for_items:
                        if node_of_type.is_initial() and item in node_of_type.vpath:
                            tasks.append(ConfigTask(node, node_of_type, desc, "task_{0}".format(node_of_type.name),
                                                    "task_{0}".format(str(i)))
                                         )
                            i += 1

        return tasks

    def _pass_callback(self, api):
        pass
