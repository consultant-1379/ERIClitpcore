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
from litp.core.execution_manager import CallbackTask, ConfigTask


class DeconfigPlugin(Plugin):
    """
    LITP Mock volmgr plugin to provide snapshots tasks in ats
    """

    def create_configuration(self, plugin_api_context):
        tasks = []
        nodes = plugin_api_context.query("node")
        for node in nodes:
            for vg in node.storage_profile.volume_groups:
                for fs in vg.file_systems:
                    if fs.is_initial():
                        tasks.append(
                            ConfigTask(node, fs, 'Create', 'file-system', fs.item_id, **self._get_values(fs))
                        )
                    elif fs.is_updated():
                        t1 = ConfigTask(node, fs, 'Deconfigure', 'file-system', 'old_mount', **self._get_removal_values(fs))
                        t1.persist = False
                        t2 = ConfigTask(node, fs, 'Update', 'file-system', fs.item_id, **self._get_values(fs))
                        t2.requires.add(t1)
                        tasks.append(t1)
                        tasks.append(t2)
        return tasks

    def create_snapshot_plan(self, plugin_api_context):
        return []

    def _do_stuff(self, callback_api):
        return

    def _get_values(self, item):
        # get values from items properties for removal task
        values = item.properties
        values['ensure'] = "present"
        return values
    def _get_removal_values(self, item):
        # get values from items properties for removal task
        values = item.properties
        values['ensure'] = "absent"
        return values
