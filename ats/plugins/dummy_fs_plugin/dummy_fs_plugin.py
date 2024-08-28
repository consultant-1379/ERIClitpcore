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


class DummyFSPlugin(Plugin):
    """
    LITP Mock volmgr plugin to provide snapshots tasks in ats
    """

    def create_configuration(self, plugin_api_context):
        tasks = []
        nodes = plugin_api_context.query("node")
        for node in nodes:
            for vg in node.storage_profile.volume_groups:
                for fs in vg.file_systems:
                    tasks.append(
                        ConfigTask(node, fs, 'filesystem', 'Fake_Puppet_resource_type', 'unique_fs_id')
                    )
        return tasks

    def create_snapshot_plan(self, plugin_api_context):
        return []

    def _do_stuff(self, callback_api):
        return
