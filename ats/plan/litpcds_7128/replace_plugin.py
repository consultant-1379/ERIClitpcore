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


class ReplacePlugin(Plugin):
    """
    LITP Mock item plugin for testing.
    """

    def create_configuration(self, plugin_api_context):
        tasks = []
        nodes = plugin_api_context.query("node") + \
                plugin_api_context.query("ms")
        for node in nodes:
            for item in node.query("replaceable", is_initial=True):
                tasks.append(
                    ConfigTask(node, item, "Initial setup", "item",
                               item.name,
                               **self._get_values(item))
                )
        for node in nodes:
            for item in node.query("replaceable", is_updated=True):
                tasks.append(
                    ConfigTask(node, item, "Update", "item",
                               item.name,
                               **self._get_values(item))
                )
        for node in nodes:
            for item in node.query("replaceable", is_for_removal=True):
                tasks.append(
                    ConfigTask(node, item, "Deconfigure", "item",
                               item.name,
                               **self._get_removal_values(item))
                )
        return tasks

    def _get_values(self, item, applied=False):
        # get configuration values from items properties for a task
        values = {}
        values['ensure'] = "present"
        values.update(item.properties)
        return values

    def _get_removal_values(self, item, applied=True):
        # get values from items properties for removal task
        values = self._get_values(item, applied)
        values['ensure'] = "absent"
        return values
