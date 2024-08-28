from litp.core.plugin import Plugin
from litp.core.task import ConfigTask


class DeconfigureTasksPlugin(Plugin):
    run = 0

    def __init__(self, *args, **kwargs):
        super(DeconfigureTasksPlugin, self).__init__(*args, **kwargs)

    def create_configuration(self, api):
        self.run += 1
        if self.run == 1:
            return self.create_configuration_1(api)
        else:
            return []

    def create_configuration_1(self, api):
        tasks = []
        for node in sorted(api.query("node") + api.query("ms")):
            for item in node.query("storage-profile-base"):
                task = ConfigTask(node, item, "Storage ConfigTask (deconfigure task on node1)", "storage_task", "t1", t=self.run)
                if node.hostname == "node1":
                    task.persist = False
                tasks.append(task)
            for item in node.query("software-item"):
                task = ConfigTask(node, item, "Generic software ConfigTask", "software_task", "t1", t=self.run)
                tasks.append(task)
        return tasks

