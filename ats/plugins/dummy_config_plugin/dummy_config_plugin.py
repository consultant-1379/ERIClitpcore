from litp.core.plugin import Plugin
from litp.core.task import ConfigTask


class ConfigPlugin(Plugin):
    def create_configuration(self, plugin_api_context):
        tasks = []
        for node in plugin_api_context.query("node"):
            for cfg in node.query("node-config"):
                if cfg.item_type_id != 'firewall-node-config':
                    tasks.append(
                        ConfigTask(node, cfg,
                                   "dummy cfg task",
                                   "dummy::cfg", "123"))

        return tasks
