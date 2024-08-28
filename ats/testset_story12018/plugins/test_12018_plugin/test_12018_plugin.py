from litp.core.plugin import Plugin
from litp.core.task import ConfigTask
from litp.core.task import CallbackTask
from litp.core.litp_logging import LitpLogger
log = LitpLogger()

class Test12018Plugin(Plugin):

    def create_configuration(self, api):
        return self.create_configuration_1(api)

    def create_configuration_1(self, api):
        tasks = []
        for node in api.query("node"):
            log.trace.debug("Node {0}".format(node))
            # Pass node1 child task, fail node2 child task
            if node.hostname == "node1":
                callback = self._pass_callback
                desc = "Pass"
                for parent in node.query("parent"):
                    parent_task = CallbackTask(parent, desc, callback)
                    tasks.append(parent_task)
                for child in node.query("child"):
                    child_task = CallbackTask(child, desc, callback)
                    tasks.append(child_task)
                for grandchild in node.query("grand-child"):
                    grandchild_task = CallbackTask(grandchild, desc, callback)
                    tasks.append(grandchild_task)

            else:
                desc = "Fail or never executes."
                for parent in node.query("parent"):
                    callback = self._fail_callback
                    parent_task = CallbackTask(parent, desc, callback)
                    tasks.append(parent_task)
                for child in node.query("child"):
                    callback = self._fail_child_callback
                    child_task = CallbackTask(child, desc, callback)
                    tasks.append(child_task)
                for grandchild in node.query("grand-child"):
                    callback = self._fail_gc_callback
                    grandchild_task = CallbackTask(grandchild, desc, callback)
                    tasks.append(grandchild_task)
        log.trace.debug("ALL TASKS: {0}".format(tasks))
        return tasks

    def create_lock_tasks(self, api, node):
        ms = api.query("ms")[0]
        return (
            ConfigTask(ms, node, "lock ConfigTask", "node_lock", "blah1"),
            ConfigTask(ms, node, "unlock ConfigTask", "node_unlock", "blah2"),
        )

    def _fail_callback(self, api):
        raise Exception

    def _fail_child_callback(self, api):
            raise Exception

    def _fail_gc_callback(self, api):
        raise Exception

    def _pass_callback(self, api):
        raise Exception
