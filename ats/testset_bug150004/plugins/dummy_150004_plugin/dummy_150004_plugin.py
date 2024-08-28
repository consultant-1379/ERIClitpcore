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


class Dummy150004Plugin(Plugin):

    def create_configuration(self, plugin_api_context):
        tasks = []
        # Tasks to transition the whole model to applied
        nodes = plugin_api_context.query("node") + \
                plugin_api_context.query("ms")
        for node in nodes:
            if node.is_initial():
                tasks.append(
                    CallbackTask(
                        node,
                        'Set up node {0}'.format(node.hostname),
                        self._do_stuff
                    )
                )
        return tasks

    def create_snapshot_plan(self, plugin_api_context):
        tasks = []
        plan_operation = plugin_api_context.snapshot_action()
        if plan_operation == 'create':
            nodes = plugin_api_context.query("node") + \
                    plugin_api_context.query("ms")

            for node in nodes:
                tasks.append(
                    CallbackTask(
                        node,
                        'Create snapshot on {0}'.format(node.hostname),
                        self._do_stuff
                    )
                )
        elif plan_operation == 'restore':
            snapshot_model = plugin_api_context.snapshot_model()
            snapshot_nodes = snapshot_model.query("node") + \
                    snapshot_model.query("ms")
            for node in snapshot_nodes:
                tasks.append(
                    CallbackTask(
                        node,
                        'Restore snapshot on {0}'.format(node.hostname),
                        self._do_stuff
                    )
                )
                if not node.is_ms():
                    cluster = node.get_cluster()
                    tasks.append(
                        CallbackTask(
                            cluster,
                            'Restart cluster {0}'.format(cluster.item_id),
                            self._restart_node
                        )
                    )

        return tasks

    def _do_stuff(self, callback_api):
        return

    def _restart_node(self, callback_api):
        return
