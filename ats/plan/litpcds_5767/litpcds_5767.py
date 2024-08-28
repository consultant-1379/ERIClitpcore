##############################################################################
# COPYRIGHT Ericsson AB 2013
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################

from litp.core.plugin import Plugin
from litp.core.extension import ModelExtension
from litp.core.model_type import ItemType
from litp.core.execution_manager import ConfigTask


class TestExtension(ModelExtension):
    def define_item_types(self):
        return [
            ItemType(
                "firewall-node-config",
                extend_item="node-config",
            )
        ]


class TestPlugin(Plugin):

    def validate_model(self, plugin_api_context):
        return []

    def create_configuration(self, plugin_api_context):
        tasks = []
        ms = plugin_api_context.query('ms')[0]

        for fsystem in ms.file_systems:
            tasks.append(ConfigTask(ms, fsystem, 'ms nfs task',
                                    'nfs::nfs_mount', 'nfs'))

        for config in ms.configs:
            if config.item_type_id == 'firewall-node-config':
                tasks.append(ConfigTask(ms, config, 'ms fw cfg task',
                                        'cfg::fw', 'fw'))
            else:
                tasks.append(ConfigTask(ms, config, 'ms regular cfg task',
                                        'cfg::config', 'cfg'))
        return tasks
