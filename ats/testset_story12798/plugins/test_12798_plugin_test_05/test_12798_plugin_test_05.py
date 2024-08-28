from litp.core.plugin import Plugin
from litp.core.task import ConfigTask
from litp.core.task import CallbackTask
from litp.core.litp_logging import LitpLogger

log = LitpLogger()


class Test12798Plugin_test_05(Plugin):
    """ plugin for test 6,7,8 """
    def create_configuration(self, plugid_api_context):
        tasks = []
        tasks_for_items = ['item1', 'item2', 'item3', 'item4']
        types = ['parent', 'child', 'g-child', 'g-g-child']
        desc = "Some Task Description"

        for node in plugid_api_context.query("ms"):
            i = 0
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
