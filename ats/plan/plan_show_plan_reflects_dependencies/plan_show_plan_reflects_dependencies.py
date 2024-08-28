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
from litp.core.execution_manager import ConfigTask


class TestPlugin(Plugin):

    def validate_model(self, plugin_api_context):
        return []

    def create_configuration(self, plugin_api_context):
        tasks = []
        ms = plugin_api_context.query('ms')[0]

        tasks = [
            ConfigTask(ms, ms.items, 'ms items task',
                       'ms::items', '1'),
            ConfigTask(ms, ms.routes, 'ms routes task',
                       'ms::routes', '2'),
            ConfigTask(ms, ms.services, 'ms services task',
                       'ms::services', '3'),
            ConfigTask(ms, ms.configs, 'ms configs task',
                       'ms::configs', '4'),
            ConfigTask(ms, ms.file_systems, 'ms file_systems task',
                       'ms::file_systems', '5'),
            ConfigTask(ms, ms.network_interfaces,
                       'ms network_interfaces task',
                       'ms::network_interfaces', '6'),
        ]
        tasks[0].requires.add(('ms::routes', '2'))
        return tasks
