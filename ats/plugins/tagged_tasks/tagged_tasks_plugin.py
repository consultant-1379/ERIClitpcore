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
from litp.core.execution_manager import CallbackTask

from litp.plan_types.restore_snapshot import restore_snapshot_tags


class TaggedTasksPlugin(Plugin):

    def create_configuration(self, plugin_api_context):
        return []

    def create_snapshot_plan(self, plugin_api_context):
        tasks = []
        nodes = plugin_api_context.query("node") + \
                plugin_api_context.query("ms")
        for node in nodes:
            tasks.append(
                CallbackTask(node, 'snapshot', self._do_stuff,
                             tag_name=restore_snapshot_tags.SAN_LUN_TAG)
            )
            tasks.append(
                CallbackTask(node, 'snapshot', self._do_stuff, tag_name=None)
            )
        return tasks

    def _do_stuff(self, callback_api):
        return
