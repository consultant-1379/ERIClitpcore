from litp.core.plugin import Plugin
from litp.core.task import ConfigTask


class ConfigTaskDepsPlugin(Plugin):

    def create_configuration(self, api):
        tasks = []

        for node in sorted(api.query("node")):
                if node.is_initial():
                    task1 = ConfigTask(node, node, "ConfigTask 1", "file1", "a")
                    tasks.append(task1)
                if node.is_updated():
                    task2 = ConfigTask(node, node, "ConfigTask 2", "file2", 'b')
                    task2.requires.add(('file1', 'a'))
                    tasks.append(task2)

        return tasks
