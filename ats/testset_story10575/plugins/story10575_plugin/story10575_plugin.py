from litp.core.plugin import Plugin
from litp.core.task import ConfigTask


class Story10575Plugin(Plugin):
    """Test plugin for LITPCDS-10575"""

    def create_configuration(self, api):
        tasks = []
        for node in api.query('node'):
            for item in node.query('story10575', is_initial=True,
                    config='true'):
                tasks.append(ConfigTask(node, item,
                        'Configure {0} package'.format(item.name),
                        'package', item.name + '_package',
                        configure="initial"))
                tasks.append(ConfigTask(node, item,
                        'Configure {0} file'.format(item.name),
                        'file', item.name + '_file',
                        configure="initial"))
            for item in node.query('story10575', is_for_removal=True,
                    deconfig='true'):
                tasks.append(ConfigTask(node, item,
                        'Deconfigure {0} package'.format(item.name),
                        'package', item.name + '_package',
                        configure="for_removal"))
                tasks.append(ConfigTask(node, item,
                        'Deconfigure {0} file'.format(item.name),
                        'file', item.name + '_file',
                        configure="for_removal"))
        return tasks
