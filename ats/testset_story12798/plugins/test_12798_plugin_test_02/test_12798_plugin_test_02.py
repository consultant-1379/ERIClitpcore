from litp.core.plugin import Plugin
from litp.core.task import ConfigTask
from litp.core.task import CallbackTask
from litp.core.litp_logging import LitpLogger

log = LitpLogger()


class Test12798Plugin_test_02(Plugin):

    def create_configuration(self, plugid_api_context):
        tasks = []

        for node in plugid_api_context.query("ms"):

            callback = self._pass_callback
            desc = "Pass"
            for parent in node.query("file-system"):
                parent_task = CallbackTask(parent, desc, callback)
                tasks.append(parent_task)
            for child in node.query("child"):
                child_task = CallbackTask(child, desc, callback)
                tasks.append(child_task)
            for g_child in node.query("my-file-system"):
                grandchild_task = CallbackTask(g_child, desc, callback)
                tasks.append(grandchild_task)

        for node in plugid_api_context.query("node"):

            callback = self._pass_callback
            desc = "Pass"
            for parent in node.query("file-system"):
                parent_task = CallbackTask(parent, desc, callback)
                tasks.append(parent_task)
            for child in node.query("child"):
                child_task = CallbackTask(child, desc, callback)
                tasks.append(child_task)
            for g_child in node.query("my-file-system"):
                grandchild_task = CallbackTask(g_child, desc, callback)
                tasks.append(grandchild_task)

        return tasks

    def _pass_callback(self, api):
        pass


