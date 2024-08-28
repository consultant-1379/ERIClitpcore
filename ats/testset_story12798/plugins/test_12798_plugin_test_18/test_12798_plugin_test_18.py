from litp.core.plugin import Plugin
from litp.core.task import ConfigTask
from litp.core.task import CallbackTask
from litp.core.litp_logging import LitpLogger

log = LitpLogger()


class Test12798Plugin_test_18(Plugin):
    """ Mixed state plugin """
    def create_configuration(self, api):
        tasks = []
        for node in api.query("node"):
            #log.trace.debug("Node {0}".format(node))
            # Pass node1 child task, fail node2 child task
            if node.hostname == "node1":
                desc = "Pass"
                for parent in node.query("parent"):
                    if parent.is_initial():
                        parent_task = ConfigTask(node, parent, desc, "foo1", "bar1{0}".format(parent.name))
                        tasks.append(parent_task)
                for child in node.query("child"):
                    if child.is_initial():
                        child_task = ConfigTask(node, child, desc, "foo2", "bar2{0}".format(child.name))
                        tasks.append(child_task)
                for grandchild in node.query("g-child"):
                    if grandchild.is_initial():
                        grandchild_task = ConfigTask(node, grandchild, desc, "foo3{0}".format(grandchild.name), "bar3{0}".format(grandchild.name))
                        tasks.append(grandchild_task)

            else:
                desc = "Fail or never executes."
                for parent in node.query("parent"):
                    if parent.is_initial():
                        parent_task = ConfigTask(node, parent, desc, "foo4", "bar4{0}".format(parent.name))
                        tasks.append(parent_task)
                for child in node.query("child"):
                    if child.is_initial():
                        child_task = ConfigTask(node, child, desc, "foo5{0}".format(child.name), "bar5{0}".format(child.name))
                        tasks.append(child_task)
                for grandchild in node.query("g-child"):
                    if grandchild.is_initial():
                        grandchild_task = ConfigTask(node, grandchild, "foo6{0}".format(grandchild.name), "foo6{0}".format(grandchild.name), "bar6{0}".format(grandchild.name))
                        tasks.append(grandchild_task)
        #log.trace.debug("ALL TASKS: {0}".format(tasks))
        return tasks
