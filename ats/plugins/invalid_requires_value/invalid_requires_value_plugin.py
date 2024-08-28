from litp.core.plugin import Plugin
from litp.core.task import ConfigTask


class InvalidRequiresValuePlugin(Plugin):
    def create_configuration(self, api):
        node = api.query('node')[0]
        task = ConfigTask(node, node, "Invalid 'requires' set", "1", "1")
        task.requires.add(None)
        return [task]
