from litp.core.plugin import Plugin
from litp.core.task import ConfigTask
from litp.core.litp_logging import LitpLogger
log = LitpLogger()

class Depend10650Plugin(Plugin):
    """Test plugin for LITPCDS-10650"""

    def create_configuration(self, api):
        tasks = []
        task = None

        for node in api.query("node"):
            # TC02
            #for item in node.query(
            #        "depend10650", name="tc15_depend"):
            for item in node.query("depend10650"):
                if item.name=="tc15_depend" or item.name=="tc16_depend":
                    log.trace.debug("10650:item: {0}".format(item))
                    task = ConfigTask(
                        node, item, "", "baz1", "qux1", name=item.name)
                    log.trace.debug("10650:task: {0}".format(task))
                    tasks.append(task)

            for item in node.query(
                    "depend10650", name="tc15_depend2"):
                task = ConfigTask(
                    node, item, "", "baz2", "qux2", name=item.name)
                task.replaces.add(("baz1", "qux1"))
                task.requires.add(("foo1", "bar1"))
                tasks.append(task)

        return tasks
