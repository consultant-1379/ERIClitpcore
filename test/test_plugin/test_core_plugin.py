##############################################################################
# COPYRIGHT Ericsson AB 2013
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################

from litp.core.validators import ValidationError
from litp.plugins.core.core_plugin import CorePlugin
from litp.core.exceptions import CallbackExecutionException
from litp.core.rpc_commands import RpcExecutionException
import litp.core.constants as constants
from mock import patch, MagicMock

from base_plugin_testcase import BasePluginTestCase


class CorePluginTest(BasePluginTestCase):
    def setUp(self):
        self.plugin = CorePlugin()
        super(CorePluginTest, self).setUp()

    def _ensure_clusters_exist(self, cluster_names,
                               path_prefix='/deployments/d1/clusters/'):
        clusters = []
        for cluster_id in cluster_names:
            path = "{0}{1}".format(path_prefix, cluster_id)
            clusters.append(self.model.create_item("cluster", path))
        return clusters

    def _prepare_core_plugin_networks(self):
        self.model.create_item("node", "/node1", hostname="node1")
        self.model.create_item("network", "/networks/net1", name="mgmt")
        self.model.create_item("network", "/networks/net2", name="mgmt")

    def _prepare_clustered_service(self):
        self.model.create_item("cluster", "/cluster1")
        self.model.create_item("node", "/cluster1/nodes/node1",
                               hostname="node1")
        self.model.create_item("node", "/cluster1/nodes/node2",
                               hostname="node2")

    def _prepare_siblings_in_dependency(self, cluster_names=('c1',)):
        self.model.create_item("deployment", "/deployments/d1")
        clusters = self._ensure_clusters_exist(cluster_names)
        return clusters[0] if len(clusters) == 1 else clusters

    def test_core_plugin_networks_with_same_name(self):
        self._prepare_core_plugin_networks()
        self.assertEqual([
            ValidationError(
                '/networks/net2',
                error_message="Network name '%s' already used by '%s'" %
                ('mgmt', '/networks/net1')
            )
        ], self.plugin._validate_network_unique_names(self.plugin_api_context))

    def test_core_plugin_networks_with_same_name_no_validation(self):
        self._prepare_core_plugin_networks()
        self.model.remove_item("/networks/net1")
        self.assertEqual([],
                         self.plugin._validate_network_unique_names(self.plugin_api_context))

    def test_validate_single_sshd_config_on_ms(self):
        expected_error1 = ValidationError(error_message='There must be precisely one sshd-config Item. None found')
#       self.assertEqual([expected_error1], self.plugin._validate_single_sshd_config_on_ms(self.plugin_api_context))

        return_values = []
        itemtype = 'sshd-config'
        return_values.append(self.model.create_item('ms', '/ms'))
        ms_path1 = '/ms/configs/sshd_config'
        return_values.append(self.model.create_item(itemtype, ms_path1))
        self.assertEqual([], self.plugin._validate_single_sshd_config_on_ms(self.plugin_api_context))

        non_ms_path2 = '/configs/sc1'
        return_values.append(self.model.create_item(itemtype, non_ms_path2))

        expected_vpath_errors = ", ".join([non_ms_path2, ms_path1])

        for ret_val in return_values:
            self.assertFalse(isinstance(ret_val, list))

        expected_err2 = ValidationError(item_path=expected_vpath_errors,
                        error_message="One %s item supported, more found: %s, %s" % (itemtype, non_ms_path2, ms_path1))

        expected_err3 = ValidationError(item_path=non_ms_path2,
                                        error_message='This ItemType is only supported on the MS')

        self.assertEqual([expected_err2, expected_err3],
                         self.plugin._validate_single_sshd_config_on_ms(self.plugin_api_context))

    def test_clustered_service_node_list_validation(self):
        self._prepare_clustered_service()
        self.model.create_item("clustered-service",
                               "/cluster1/services/service1",
                               node_list="node1,node2")

        self.assertEqual([],
                         self.plugin._validate_clustered_service_node_list(self.plugin_api_context))

    def test_clustered_service_node_list_validation_no_node_fail(self):
        self._prepare_clustered_service()
        self.model.create_item("clustered-service",
                               "/cluster1/services/service1",
                               node_list="node1,node3")

        self.assertEqual([
            ValidationError(
                "/cluster1/services/service1",
                error_message='Node "/cluster1/nodes/node3" does not '
                'exist. Ensure node_list property is correct'
            )],
            self.plugin._validate_clustered_service_node_list(
                self.plugin_api_context))

    def test_clustered_service_node_list_validation_duplicate_node_fail(self):
        self._prepare_clustered_service()
        self.model.create_item("clustered-service",
                               "/cluster1/services/service1",
                               node_list="node1,node1,node2")
        self.assertEqual([
            ValidationError(
                "/cluster1/services/service1",
                error_message='Only one occurrence of a node with item_id'
                ' "node1" is allowed in node_list. Ensure'
                ' node_list property is correct'
            )],
            self.plugin._validate_clustered_service_node_list(
                self.plugin_api_context))

    def test_clustered_service_dependency_list_validation(self):
        self._prepare_clustered_service()
        self.model.create_item("clustered-service",
                               "/cluster1/services/service1",
                               node_list="node1,node2",
                               dependency_list="service2")
        self.model.create_item("clustered-service",
                               "/cluster1/services/service2",
                               node_list="node1,node2",)
        self.assertEqual([],
            self.plugin._validate_clustered_service_dependency_list(
                self.plugin_api_context))

    def test_clustered_service_dependency_list_validation_fail(self):
        self._prepare_clustered_service()
        self.model.create_item("clustered-service",
                               "/cluster1/services/service1",
                               node_list="node1,node2",
                               dependency_list="service2")
        self.assertEqual([
            ValidationError(
                "/cluster1/services/service1",
                error_message="'/cluster1/services/service2' does not "
                "exist. Please ensure dependency_list property is correct"
            )],
            self.plugin._validate_clustered_service_dependency_list(
                self.plugin_api_context))

    def test_clustered_service_can_not_depend_on_self_validation(self):
        self._prepare_clustered_service()
        self.model.create_item("clustered-service",
                               "/cluster1/services/service1",
                               node_list="node1,node2",
                               dependency_list="service1")
        self.assertEqual([
            ValidationError(
                "/cluster1/services/service1",
                error_message="A service can not depend on itself. Please "
                "ensure dependency_list property is correct"
            )],
            self.plugin._validate_clustered_service_does_not_depend_on_self(
                self.plugin_api_context))

    def test_duplicate_hostnames_on_ms_and_node(self):
        self.model.create_item("ms", "/ms", hostname="foo")
        self.model.create_item("cluster", "/cluster1")
        self.model.create_item("node", "/cluster1/nodes/node1",
                hostname="foo")

        expected_error = ValidationError(item_path="/cluster1/nodes/node1",
                error_message="Hostname 'foo' is duplicated across "
                "/cluster1/nodes/node1, /ms. All hostnames must be"
                " unique.")
        self.assertEqual([expected_error],
                self.plugin._validate_duplicate_hostnames(
                    self.plugin_api_context
                )
            )

    def test_duplicate_hostnames_on_nodes(self):
        self.model.create_item("cluster", "/cluster1")
        self.model.create_item("node", "/cluster1/nodes/Z",
                hostname="foo")
        self.model.create_item("node", "/cluster1/nodes/node2",
                hostname="bar")
        self.model.create_item("node", "/cluster1/nodes/A",
                hostname="foo")

        expected_error = ValidationError(item_path="/cluster1/nodes/A",
                error_message="Hostname 'foo' is duplicated across "
                "/cluster1/nodes/A, /cluster1/nodes/Z. All hostnames"
                " must be unique.")
        self.assertEqual([expected_error],
                self.plugin._validate_duplicate_hostnames(
                    self.plugin_api_context
                )
            )

    def test_duplicate_hostnames_case_insensitive(self):
        self.model.create_item("ms", "/ms", hostname="alpha")
        self.model.create_item("cluster", "/cluster1")
        self.model.create_item("node", "/cluster1/nodes/node1",
                hostname="ALPHA")

        expected_error = ValidationError(item_path="/cluster1/nodes/node1",
                error_message="Hostname 'alpha' is duplicated across "
                "/cluster1/nodes/node1, /ms. All hostnames must be"
                " unique.")
        self.assertEqual([expected_error],
                self.plugin._validate_duplicate_hostnames(
                    self.plugin_api_context
                )
            )

    def test_validate_error_for_over_max_siblings_in_dependency_list(self):
        cluster = self._prepare_siblings_in_dependency()

        cluster_names = ["cluster_%s" % i for i in range(1, 11)]
        cluster.set_property('dependency_list', ','.join(cluster_names))

        # Ensure all clusters exist
        self._ensure_clusters_exist(cluster_names)
        errors = self.plugin._validate_cluster_dependency_list(
            self.plugin_api_context)

        self.assertTrue(isinstance(errors, list))
        self.assertEquals(1, len(errors))

        error = errors[0]
        self.assertTrue(isinstance(error, ValidationError))
        self.assertEqual(error.error_message,
                         "A cluster cannot specify more than 9 sibling "
                         "dependencies")
        self.assertEqual(error.item_path, cluster.get_vpath())
        self.assertEqual(error.property_name, "dependency_list")

    def test_validate_no_error_for_fewer_than_max_siblings_in_dependency_list(self):
        cluster = self._prepare_siblings_in_dependency()

        cluster_names = ["cluster_%s" % i for i in range(1, 9)]
        cluster.set_property('dependency_list', ','.join(cluster_names))

        # Ensure all clusters exist
        self._ensure_clusters_exist(cluster_names)
        errors = self.plugin._validate_cluster_dependency_list(
            self.plugin_api_context)

        self.assertTrue(isinstance(errors, list))
        self.assertEquals(0, len(errors))
        self.assertEquals([], errors)

    def test_validate_error_on_self_dependency(self):
        cluster = self._prepare_siblings_in_dependency()

        cluster.set_property('dependency_list', 'c1')

        errors = self.plugin._validate_cluster_dependency_list(
            self.plugin_api_context)

        self.assertTrue(isinstance(errors, list))
        self.assertEquals(1, len(errors))

        error = errors[0]
        self.assertTrue(isinstance(error, ValidationError))
        self.assertEqual(error.error_message,
                         "A cluster cannot depend on itself. Please ensure "
                         "dependency_list property is correct")
        self.assertEqual(error.item_path, cluster.get_vpath())
        self.assertEqual(error.property_name, "dependency_list")

    def test_validate_error_for_missing_sibling_cluster(self):
        cluster = self._prepare_siblings_in_dependency()

        cluster_names = ["cluster_%s" % i for i in range(1, 8)]
        cluster.set_property('dependency_list', 'absent')

        # Ensure all clusters exist
        self._ensure_clusters_exist(cluster_names)
        errors = self.plugin._validate_cluster_dependency_list(
            self.plugin_api_context)

        self.assertTrue(isinstance(errors, list))
        self.assertEquals(1, len(errors))

        error = errors[0]
        self.assertTrue(isinstance(error, ValidationError))
        self.assertEqual(error.error_message,
                         "Cluster \"/deployments/d1/clusters/absent\" does not "
                         "exist. Ensure dependency_list property is correct")
        self.assertEqual(error.item_path, cluster.get_vpath())
        self.assertEqual(error.property_name, "dependency_list")

    def test_validate_error_for_removal_dependant_cluster(self):
        cluster, cluster2 = self._prepare_siblings_in_dependency(('c1', 'c2'))

        cluster.set_property('dependency_list', '')
        cluster2.set_property('dependency_list', 'c1')

        cluster.set_for_removal()

        errors = self.plugin._validate_cluster_dependency_list(
            self.plugin_api_context)

        self.assertTrue(isinstance(errors, list))
        self.assertEquals(1, len(errors))

        error = errors[0]
        self.assertTrue(isinstance(error, ValidationError))
        expected_error = ('Cluster "/deployments/d1/clusters/c1" is for '
                          'removal. Cluster "/deployments/d1/clusters/c2" '
                          'has a dependency on it and is not for removal')
        self.assertEqual(error.error_message,expected_error)
        self.assertEqual(error.item_path, cluster2.get_vpath())
        self.assertEqual(error.property_name, "dependency_list")

    def test_validate_no_error_for_removal_sibling_cluster(self):
        cluster, cluster2 = self._prepare_siblings_in_dependency(('c1', 'c2'))

        cluster.set_property('dependency_list', '')
        cluster2.set_property('dependency_list', 'c1')

        cluster.set_for_removal()
        cluster2.set_for_removal()

        errors = self.plugin._validate_cluster_dependency_list(
            self.plugin_api_context)

        self.assertTrue(isinstance(errors, list))
        self.assertEquals(0, len(errors))

    def test_validate_error_for_duplicate_sibling_dependency(self):
        cluster = self._prepare_siblings_in_dependency()

        cluster_names = ["cluster_%s" % i for i in range(1, 8)]

        # Ensure all clusters exist
        self._ensure_clusters_exist(cluster_names)

        cluster.set_property('dependency_list',
                             ','.join(cluster_names) + ',cluster_1')
        errors = self.plugin._validate_cluster_dependency_list(
            self.plugin_api_context)

        self.assertTrue(isinstance(errors, list))
        self.assertEquals(1, len(errors))

        error = errors[0]
        self.assertTrue(isinstance(error, ValidationError))
        self.assertEqual(error.error_message,
                         "Only one occurrence of a cluster with item_id "
                         "\"cluster_1\" is allowed in dependency_list. Ensure "
                         "dependency_list property is correct")
        self.assertEqual(error.item_path, cluster.get_vpath())
        self.assertEqual(error.property_name, "dependency_list")

    def test_validate_no_error_for_no_cyclical_dependencies(self):
        cluster, cluster2, cluster3 = \
            self._prepare_siblings_in_dependency(('c1', 'c2', 'c3'))

        cluster3.set_property('dependency_list', 'c1')
        cluster2.set_property('dependency_list', 'c1')
        cluster.set_property('dependency_list', '')
        errors = self.plugin._validate_cluster_no_cyclical_dependencies(
            self.plugin_api_context)

        self.assertTrue(isinstance(errors, list))
        self.assertEquals([], errors)

    def test_validate_error_for_cyclical_dependencies(self):
        cluster, cluster2, cluster3, cluster4 = \
            self._prepare_siblings_in_dependency(('c1', 'c2', 'c3', 'c4'))

        cluster3.set_property('dependency_list', 'c1')
        cluster2.set_property('dependency_list', 'c3')
        cluster.set_property('dependency_list', 'c2')
        errors = self.plugin._validate_cluster_no_cyclical_dependencies(
            self.plugin_api_context)

        self.assertTrue(isinstance(errors, list))
        self.assertEquals(1, len(errors))

        error = errors[0]
        self.assertTrue(isinstance(error, ValidationError))
        self.assertEqual('A circular dependency has been detected between '
                'the following clusters: "c1", "c2" and "c3". '
                'Check the "dependency_list" property of each cluster '
                'item to resolve the issue.',
                error.error_message)
        self.assertEqual(error.item_path, cluster.parent.get_vpath())

        cluster2.set_property('dependency_list', u'c1')
        cluster4.set_property('dependency_list', u'c2')
        cluster.set_property('dependency_list', u'c4')
        cluster3.set_property('dependency_list', '')

        errors = self.plugin._validate_cluster_no_cyclical_dependencies(
            self.plugin_api_context)

        self.assertTrue(isinstance(errors, list))
        self.assertEquals(1, len(errors))

        error = errors[0]
        self.assertTrue(isinstance(error, ValidationError))
        self.assertEqual('A circular dependency has been detected between '
                'the following clusters: "c1", "c2" and "c4". '
                'Check the "dependency_list" property of each cluster '
                'item to resolve the issue.',
                error.error_message)
        self.assertEqual(error.item_path, cluster.parent.get_vpath())

    def test_circular_refs(self):
        graph = {
            'a': set(['b']),
            'b': set(['a']),
        }
        try:
            self.plugin._topsort(graph)
            self.fail("Should have thrown")
        except AssertionError:
            raise
        except Exception, e:
            self.assertEquals("A cyclic dependency exists in graph "
                              "[('a', set(['b'])), ('b', set(['a']))]", str(e))

    def test_validate_no_error_for_empty_dependency_list(self):
        cluster = self._prepare_siblings_in_dependency()

        cluster_names = ["cluster_%s" % i for i in range(1, 9)]
        cluster.set_property('dependency_list', "")

        # Ensure all clusters exist
        self._ensure_clusters_exist(cluster_names)
        errors = self.plugin._validate_cluster_dependency_list(
            self.plugin_api_context)

        self.assertTrue(isinstance(errors, list))
        self.assertEquals(0, len(errors))
        self.assertEquals([], errors)

    def test_validate_no_error_for_absent_dependency_list(self):
        cluster = self._prepare_siblings_in_dependency()

        cluster_names = ["cluster_%s" % i for i in range(1, 9)]
        cluster.delete_property('dependency_list')

        # Ensure all clusters exist
        self._ensure_clusters_exist(cluster_names)
        errors = self.plugin._validate_cluster_dependency_list(
            self.plugin_api_context)

        self.assertTrue(isinstance(errors, list))
        self.assertEquals(0, len(errors))
        self.assertEquals([], errors)

    def test_validate_no_error_on_undefined_property(self):
        self.model.create_item("deployment", "/deployments/d1")

        self.model.create_item("cluster", "/deployments/d1/clusters/c1")
        self.model.create_item("cluster-base", "/deployments/d1/clusters/c2")
        self.model.create_item("old-cluster", "/deployments/d1/clusters/c3")

        errors = self.plugin._validate_cluster_dependency_list(
            self.plugin_api_context)

        self.assertEquals([], errors)

    def test_validate_reboot_plan(self):
        self._prepare_clustered_service()

        expected_err = ValidationError(
            item_path="/i/idont/exist",
            error_message="Path not found",
            error_type=constants.INVALID_LOCATION_ERROR)

        self.assertEqual([expected_err],
            self.plugin.validate_reboot_plan(self.model, "/i/idont/exist")
        )
        self.assertEqual([], self.plugin.validate_reboot_plan(
                         self.model, "/cluster1/nodes/node1")
        )

    def test_create_reboot_tasks(self):
        self._prepare_clustered_service()
        self.model.set_all_applied()
        self.model.create_item("node", "/cluster1/nodes/node3",
                               hostname="node3")

        self.assertEqual(2, len(self.plugin.create_reboot_tasks(
            self.model, '')))

        self.assertEqual(1, len(self.plugin.create_reboot_tasks(
            self.model, "/cluster1/nodes/node1")))
        # regardless of whether it is applied or initial
        self.assertEqual(1, len(self.plugin.create_reboot_tasks(
            self.model, "/cluster1/nodes/node3")))

    @patch('litp.plugins.core.core_plugin.wait_for_node_down')
    @patch('litp.plugins.core.core_plugin.wait_for_node_puppet_applying_catalog_valid')
    def test_reboot_node_and_wait(self, wfnpacv, wfnd):
        # for coverage purposes rather than UT, not much to UT
        with patch.object(self.plugin, '_execute_rpc_in_callback_task') as erc:
            self.plugin._reboot_node_and_wait(MagicMock(), 'node', True)

    @patch('litp.plugins.core.core_plugin.RpcCommandProcessorBase.execute_rpc_and_process_result')
    def test_execute_rpc_in_callback_task(self, erapr):
        erapr.return_value = ('', '')
        self.plugin._execute_rpc_in_callback_task(MagicMock, [], '', '')
        erapr.side_effect = RpcExecutionException('oops')
        self.assertRaises(CallbackExecutionException,
                          self.plugin._execute_rpc_in_callback_task,
                          MagicMock, [], '', '')
