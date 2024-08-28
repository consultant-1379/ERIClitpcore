##############################################################################
# COPYRIGHT Ericsson AB 2013
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################

from mock import MagicMock
from unittest import TestCase

from litp.core.exceptions import CallbackExecutionException, PluginError
from litp.plugins.core.puppet_manager_plugin import PuppetManagerPlugin

from base_plugin_testcase import BasePluginTestCase


class PuppetManagerPluginTest(BasePluginTestCase):
    def setUp(self):
        self.plugin = PuppetManagerPlugin()
        super(PuppetManagerPluginTest, self).setUp()
        self.plugin_api_context.snapshot_action = MagicMock(
            return_value='restore')

        self._prepare_ms()
        self.model.create_item('deployment', '/deployments/d1')
        self.ifs = self.model.create_item('infrastructure', '/infrastructure')

    def _prepare_ms(self):
        self.ms = self.model.create_item("ms", "/ms")

    def _prepare_peers(self):
        self.c1 = self.model.create_item('cluster', '/deployments/d1/clusters/c1')
        path_template = "/deployments/d1/clusters/c1/nodes/n%d"
        system_path_t = "/infrastructure/systems/sys%s"
        disk_system_path_t = "/infrastructure/systems/sys%s/disks/disk0"
        self.nodes = [self.model.create_item("node", path_template % i,
                                             hostname='node%d' % i)
                      for i in [1, 2]]

        for n in [1, 2]:
            node = self.model.get_item("/deployments/d1/clusters/c1/nodes/n%d" % n)
            # torf-129782: nodes in initial won't stop puppet
            node.set_applied()
            sys = self.model.create_item("system", system_path_t % n)
            disk = self.model.create_item("disk", disk_system_path_t % n)
            self.model.create_inherited(system_path_t % n,
                    "/deployments/d1/clusters/c1/nodes/n%d/system" % n)

    def _prepare_snapshot(self):
        self.model.create_snapshot_item('snapshot')
        self.plugin_api_context.snapshot_name = MagicMock(
            return_value='snapshot')
        # semi-real snapshot model
        self.plugin_api_context.snapshot_model = MagicMock(
            return_value=self.plugin_api_context)

    def _prepare_no_snapshot(self):
        self.plugin_api_context.snapshot_model = MagicMock(
            return_value=None)

    def test_message_format(self):
        msg = self.plugin._enumerate_nodes(['x'])
        self.assertEquals('node "x"', msg)
        msg = self.plugin._enumerate_nodes(['x', 'y'])
        self.assertEquals('nodes "x" and "y"', msg)
        msg = self.plugin._enumerate_nodes(['x', 'y', 'z'])
        self.assertEquals('nodes "x", "y" and "z"', msg)
        msg = self.plugin._enumerate_nodes(['a', 'x', 'y', 'z'])
        self.assertEquals('nodes "a", "x", "y" and "z"', msg)


    def test_restore_snapshot_httpd_callback(self):
        '''
        In normal situation:
         - all nodes have puppet stopped,
         - ms has httpd stopped.
        '''
        self._prepare_peers()
        self._prepare_snapshot()

        tasks = self.plugin.create_snapshot_plan(self.plugin_api_context)
        self.assertEquals(len(tasks), 3)

        httpd_count = 0
        puppet_count = 0

        for task in tasks:
            self.assertTrue(task.format_parameters()['call_type'] in
                            ['_stop_puppet', '_stop_service'])
            if task.description.startswith('Stop service "httpd"'):
                httpd_count += 1
                self.assertEqual('ms', task.model_item.item_type.item_type_id)
            if task.description.startswith('Stop service "puppet"'):
                puppet_count += 1
                self.assertTrue('deployment' or 'ms' in
                                 task.model_item.item_type.item_type_id)

        self.assertEqual(httpd_count, 1)
        self.assertEqual(puppet_count, 2)

    def test_restore_requires_snapshotting(self):
        '''
        Snapshot must be present on the moment of restore attempt.
        '''
        self._prepare_peers()
        self._prepare_no_snapshot()
        self.assertRaises(PluginError,
                          self.plugin.create_snapshot_plan,
                          self.plugin_api_context)

    def test_generate_puppet_tasks_when_no_peer_nodes(self):
        '''
        Lack of node-type nodes does not break the task generation.
        '''
        # remove the MS or the plan will not be empty
        # need to use the private method to get past validation error
        self.model._remove_item(self.model.get_item('/ms'))
        self._prepare_snapshot()
        tasks = self.plugin.generate_puppet_stop_callback_tasks(
            self.plugin_api_context.snapshot_model())
        self.assertEqual([], tasks)

    def test_generate_puppet_tasks_ms_only(self):
        '''
        No MNs at all, only the MS
        '''
        self._prepare_snapshot()
        tasks = self.plugin.generate_puppet_stop_callback_tasks(
            self.plugin_api_context.snapshot_model())
        self.assertEqual(1, len(tasks))
        self.assertEqual('Stop service "puppet" on node "None"',
                         tasks[0].description)

    def test_generate_puppet_tasks_when_exist_peer_nodes(self):
        '''
        Number of tasks corresponds to number of nodes.
        '''
        self._prepare_peers()
        self._prepare_snapshot()
        tasks = self.plugin.generate_puppet_stop_callback_tasks(
            self.plugin_api_context.snapshot_model())
        self.assertEqual(len(self.nodes), 2)
        self.assertEqual(len(tasks), 2)

    def test_generate_httpd_tasks_when_exist_ms_nodes(self):
        '''
        Number of tasks corresponds is exactly 1.
        '''
        self._prepare_ms()
        self._prepare_peers()
        self._prepare_snapshot()
        tasks = self.plugin.generate_httpd_stop_callback_task(
            self.plugin_api_context.snapshot_model())
        self.assertEqual(1, len(tasks))


class ServiceStopTestCase(TestCase):
    def setUp(self):
        self.callback_api = MagicMock()
        self.plugin = PuppetManagerPlugin()

    def test_no_hostnames(self):
        '''
        Empty list of hostnames leads to an exception. No RPC calls.
        '''
        service = 'foo'
        hostnames = []
        self.assertRaises(CallbackExecutionException,
                                  self.plugin._stop_service,
                                  self.callback_api, service, hostnames)
        self.assertEqual(0, len(self.callback_api.rpc_application.mock_calls))

    def test_stops_ok(self):
        '''
        Normal argument produce one RPC call.
        '''
        service = 'foo'
        hostnames = ['n1', 'n2']
        self.plugin._stop_service(self.callback_api, service, hostnames)
        self.callback_api.rpc_application.assert_called_once_with(
            hostnames,
            ['service', service, 'stop', '-y'])
