import re

from litp.core.exceptions import PluginError, CallbackExecutionException
from litp.core.plugin import Plugin
from litp.core.task import CallbackTask
from litp.plan_types.restore_snapshot import restore_snapshot_tags


class PuppetManagerPlugin(Plugin):

    """Puppet manager plugin."""

    def create_snapshot_plan(self, plugin_api_context):
        '''
        Create a plan for ``restore`` snapshot action.
        Generates stop httpd tasks for the management server.
        Also generates stop puppet tasks for peer servers of clusters
        containing model items of ``disk`` type.
        '''
        try:
            action = plugin_api_context.snapshot_action()
        except Exception as exc:
            raise PluginError(exc)

        tasks = []
        if action == 'restore':
            snapshot_model = plugin_api_context.snapshot_model()
            if not snapshot_model:
                msg = 'Snapshot model missing for %s_snapshot action' % \
                    action
                raise PluginError(msg)
            tasks.extend(self.generate_puppet_stop_callback_tasks(
                    snapshot_model))
            tasks.extend(self.generate_httpd_stop_callback_task(
                    snapshot_model))
        return tasks

    def _nodes_by_cluster_disk(self, deployment):
        disks_c = []
        for c in deployment.query('cluster'):
            has_disk = False
            # only querying disks on nodes
            nodes = c.query('node')
            for nc in nodes:
                if nc.system.query('disk'):
                    # node in Initial + APD -> node is for sure in Initial,
                    # so it is not added. Add it for the rest of the cases
                    disks_c.extend([n.hostname for n in nodes if
                                    not (nc.is_initial() and
                                    nc.applied_properties_determinable)])
                    break
        return disks_c

    def _enumerate_nodes(self, node_names):
        msg = re.sub('(.*),',
                     r'\1 and',
                     ', '.join(['"' + n + '"' for n in node_names]))
        if len(node_names) == 1:
            start_msg = 'node'
        else:
            start_msg = 'nodes'
        msg = '{0} {1}'.format(start_msg, msg)
        return msg

    def generate_puppet_stop_callback_tasks(self, snapshot_model):
        tasks = []
        for ms in snapshot_model.query('ms'):
            tasks.append(CallbackTask(
                ms,
                'Stop service "puppet" on node "{0}"'.format(ms.hostname),
                self._stop_puppet,
                [ms.hostname],
                tag_name=restore_snapshot_tags.PREPARE_PUPPET_TAG
            ))
        # word 'nodes' in the message below comes from _enumerate_nodes
        template = ('Stop service "puppet" on {0}'
                                        ' in deployment "{1}"')
        for deployment in snapshot_model.query("deployment"):
            hostnames = self._nodes_by_cluster_disk(deployment)
            if not hostnames:
                continue
            description = template.format(
                                self._enumerate_nodes(hostnames),
                                deployment.item_id
                                )
            task = CallbackTask(
                deployment,
                description,
                self._stop_puppet,
                hostnames,
                tag_name=restore_snapshot_tags.PREPARE_PUPPET_TAG
            )
            tasks.append(task)
        return tasks

    def generate_httpd_stop_callback_task(self, snapshot_model):
        ms = snapshot_model.query("ms")
        if ms:
            ms = ms[0]
            description = 'Stop service "httpd" on node "%s"' % ms.hostname
            return [CallbackTask(
                ms,
                description,
                self._stop_service,
                'httpd',
                [ms.hostname],
                tag_name=restore_snapshot_tags.PREPARE_PUPPET_TAG
            )]
        return []

    def _stop_service(self, callback_api, service, hostnames):
        if not hostnames:
            message = ("service {0} was requested to be stopped, but the node"
                       " list is empty").format(service)
            raise CallbackExecutionException(message)
        call_args = ['service', service, 'stop', '-y']
        callback_api.rpc_application(hostnames, call_args)

    def _stop_puppet(self, callback_api, hostnames):
        if not hostnames:
            message = ("service Puppet was requested to be stopped, but the"
                       " node list is empty")
            raise CallbackExecutionException(message)
        callback_api.rpc_command(hostnames, 'core', 'safe_stop_puppet',
                                 timeout=300)
