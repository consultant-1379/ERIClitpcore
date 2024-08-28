from litp.core.plugin import Plugin
from litp.core.task import ConfigTask


class NonPersistentPlugin(Plugin):
    run = 0

    def __init__(self, *args, **kwargs):
        super(NonPersistentPlugin, self).__init__(*args, **kwargs)

    def create_configuration(self, api):
        NonPersistentPlugin.run += 1
        if NonPersistentPlugin.run == 1:
            return self.create_configuration_1(api)
        elif NonPersistentPlugin.run == 2:
            return self.create_configuration_2(api)
        else:
            return []

    def create_configuration_1(self, api):
        tasks = []
        for node in sorted(api.query("node") + api.query("ms")):
            for item in node.query("software-item"):
                task = ConfigTask(node, item, "Persistent ConfigTask", "task", "t1", t=self.run)
                tasks.append(task)
        return tasks

    def create_configuration_2(self, api):
        tasks = []
        for node in sorted(api.query("node") + api.query("ms")):
            for item in node.query("software-item"):
                task = ConfigTask(node, item, "Non Persistent ConfigTask", "task", "t1", t=self.run)
                task.persist = False
                tasks.append(task)
        return tasks
