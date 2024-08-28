import unittest

from mock import Mock
from litp.core.model_manager import ModelManager, QueryItem
from litp.core.execution_manager import ExecutionManager
from litp.core.plugin_context_api import PluginApiContext
from litp.core.model_type import PropertyType
from litp.core.model_type import ItemType
from litp.core.model_type import Collection
from litp.core.model_type import Property
from litp.core.model_item import ModelItem


class SnapshotModelApiTest(unittest.TestCase):

    def setUp(self):
        self.model = ModelManager()
        self.plugin_api = PluginApiContext(self.model)
        self.manager = ExecutionManager(self.model, Mock(), Mock())

        self.model.register_property_type(PropertyType("basic_string"))
        self.model.register_property_type(PropertyType("basic_boolean", regex=r"^(true|false)$"))

        self.model.register_item_type(ItemType("root",
            nodes=Collection("node"),
            snapshots=Collection("snapshot-base"),
            deployments=Collection("deployment"),
        ))
        self.model.register_item_type(ItemType("deployment",
            clusters=Collection("cluster"),
        ))
        self.model.register_item_type(ItemType("cluster-base"))

        self.model.register_item_type(ItemType("cluster",
                                               extend_item="cluster-base",
                                               nodes=Collection("node"),
        ))
        self.model.register_item_type(ItemType("node",
            hostname=Property("basic_string", updatable_plugin=False),
        ))
        self.model.register_item_type(ItemType("snapshot-base",
                timestamp=Property('basic_string'),
                active=Property('basic_boolean',
                            required=False,
                            updatable_rest=False,
                            default='true')))

        self.model.create_root_item("root")
        self.model.create_item("deployment", "/deployments/d1")
        self.model.create_item("cluster", "/deployments/d1/clusters/c1")
        self.model.create_item("node", "/deployments/d1/clusters/c1/nodes/n2", hostname="n2")
        self.model.create_item("snapshot-base", "/snapshots/snapshot", timestamp="123")

    def test_query_and_query_by_vpath(self):
        self.model.set_all_applied()
        # Create SnapshotModelApi object
        self.manager._backup_model_for_snapshot()
        # Make chages to the current model
        n2 = self.model.remove_item("/deployments/d1/clusters/c1/nodes/n2")
        self.assertTrue(n2.is_for_removal())
        n1 = self.model.create_item("node", "/deployments/d1/clusters/c1/nodes/n1", hostname="n1")
        self.assertTrue(n1.is_initial())
        self.assertEqual(2, len(self.plugin_api.query("node")))

        # Assert the snapshot model does not have the new changes (post snapshot)
        snap_model = self.plugin_api.snapshot_model()
        snap_nodes = snap_model.query("node")
        self.assertEqual(1, len(snap_nodes))
        self.assertTrue(isinstance(snap_nodes[0], QueryItem))
        self.assertTrue(snap_nodes[0].is_applied())
        self.assertNotEqual(n2, snap_nodes[0]._model_item)

        self.assertEqual(None, snap_model.query_by_vpath("/deployments/d1/clusters/c1/nodes/n1"))

        # Assert the snapshot model had the correct items (pre snapshot)
        self.assertEqual("/deployments/d1/clusters/c1/nodes/n2", snap_nodes[0].vpath)
        self.assertEqual({u'hostname': u'n2'}, snap_nodes[0].properties)
        self.assertEqual({u'hostname': u'n2'}, snap_nodes[0].applied_properties)

        plug_cluster = self.plugin_api.query_by_vpath("/deployments/d1/clusters/c1")
        snap_cluster = snap_model.query_by_vpath("/deployments/d1/clusters/c1")
        self.assertEqual(plug_cluster, snap_cluster)
