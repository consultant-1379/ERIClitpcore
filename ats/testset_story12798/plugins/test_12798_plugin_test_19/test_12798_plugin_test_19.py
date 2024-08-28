from litp.core.plugin import Plugin
from litp.core.task import ConfigTask
from litp.core.task import CallbackTask
from litp.core.litp_logging import LitpLogger

log = LitpLogger()


class Test12798Plugin_test_19(Plugin):
    def create_configuration(self, api):
        """ Plugin  for test 19"""
        tasks = []

        callback = self._pass_callback
        desc = "Pass"
        ms = api.query("ms")[0]
        for parent in ms.query('parent'):
            if parent.is_initial():
                parent_task = CallbackTask(parent, desc, callback)
                tasks.append(parent_task)
        for child in ms.query("child"):
            if child.is_initial():
                child_task = CallbackTask(child, desc, callback)
                tasks.append(child_task)
        for g_child in ms.query("g-child"):
            if g_child.is_initial():
                grandchild_task = CallbackTask(g_child, desc, callback)
                tasks.append(grandchild_task)
        for g_g_child in ms.query("g-g-child"):
            if g_g_child.is_initial():
                grandgrandchild_task = CallbackTask(g_g_child, desc, callback)
                tasks.append(grandgrandchild_task)

        for node in api.query("node"):
            for parent in node.query('parent'):
                if parent.is_initial():
                    parent_task = CallbackTask(parent, desc, callback)
                    tasks.append(parent_task)
            for child in node.query("child"):
                if child.is_initial():
                    child_task = CallbackTask(child, desc, callback)
                    tasks.append(child_task)
            for g_child in node.query("g-child"):
                if g_child.is_initial():
                    grandchild_task = CallbackTask(g_child, desc, callback)
                    tasks.append(grandchild_task)
            for g_g_child in node.query("g-g-child"):
                if g_g_child.is_initial():
                    grandgrandchild_task = CallbackTask(g_g_child, desc, callback)
                    tasks.append(grandgrandchild_task)

        return tasks

    def _pass_callback(self, api):
        pass
