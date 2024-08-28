import unittest

from litp.core.model_manager import ModelManager
from litp.core.model_item import ModelItem
from litp.core.model_type import ItemType, PropertyType, Property, Collection
from litp.migration.operations import (AddProperty, RemoveProperty,
                                       RenameProperty, RenameItemType,
                                       BaseOperation, UpdateCollectionType)

class TestOperations(unittest.TestCase):

    def setUp(self):
        self.model = ModelManager()
        self.model.register_property_type(PropertyType("basic_string"))
        self.model.register_item_type(ItemType("node-base",
                                               prop1=Property("basic_string"),
                                               prop2=Property("basic_string"),
                                               prop3=Property("basic_string"),
                                               )
                                      )
        self.model.register_item_type(
            ItemType("node", extend_item='node-base')
        )

        self.model.register_item_type(ItemType("new-node",
                                               prop1=Property("basic_string"),
                                               prop2=Property("basic_string"),
                                               prop3=Property("basic_string"),
                                               )
                                      )
        self.model.register_item_type(ItemType("root",
                                               nodes=Collection("node")
                                               )
                                      )
        self.model.create_root_item("root")
        self.node1 = self.model.create_item("node", "/nodes/node1",
                                            prop1="abc", prop2="def")

    def _assert_state_transition(self, item, start_state, operation, end_state):
        item._set_state(start_state)
        self.assertEqual(start_state, item.get_state())
        operation.mutate_forward(self.model)
        self.assertEqual(end_state, item.get_state())

        item._set_state(start_state)
        self.assertEqual(start_state, item.get_state())
        operation.mutate_backward(self.model)
        self.assertEqual(end_state, item.get_state())

    def test_base_operation(self):
        base_operation = BaseOperation()
        try:
            base_operation.mutate_forward(self.model)
        except NotImplementedError as error:
            pass
        self.assertEqual("subclasses of BaseOperation must provide a "
                         "mutate_forward() method", str(error))
        try:
            base_operation.mutate_backward(self.model)
        except NotImplementedError as error:
            pass
        self.assertEqual("subclasses of BaseOperation must provide a "
                         "mutate_backward() method", str(error))

    def test_add_property_operation(self):
        self.assertEqual(ModelItem.Initial, self.node1.get_state())
        add_prop_operation = AddProperty("node", "prop3", "ghi")
        add_prop_operation.mutate_forward(self.model)
        self.assertTrue("prop3" in self.node1.properties)
        self.assertEquals("ghi", self.node1.prop3)
        self.assertEqual(ModelItem.Initial, self.node1.get_state())

        add_prop_operation.mutate_backward(self.model)
        self.assertFalse("prop3" in self.node1.properties)
        self.assertEqual(ModelItem.Initial, self.node1.get_state())

    def test_add_property_operation_applied_state(self):
        add_prop_operation = AddProperty("node", "prop3", "ghi")
        self._assert_state_transition(
                self.node1, ModelItem.Applied, add_prop_operation, ModelItem.Updated)

    def test_add_property_operation_for_removal_state(self):
        add_prop_operation = AddProperty("node", "prop3", "ghi")
        self._assert_state_transition(
                self.node1, ModelItem.ForRemoval, add_prop_operation, ModelItem.Updated)

    def test_add_property_operation_for_updated_state(self):
        add_prop_operation = AddProperty("node", "prop3", "ghi")
        self._assert_state_transition(
                self.node1, ModelItem.Updated, add_prop_operation, ModelItem.Updated)

    def test_remove_property_operation(self):
        self.assertEqual(ModelItem.Initial, self.node1.get_state())
        remove_prop_operation = RemoveProperty("node", "prop2", "123")
        remove_prop_operation.mutate_forward(self.model)
        self.assertFalse("prop2" in self.node1.properties)
        self.assertEquals(None, self.node1.prop3)
        self.assertEqual(ModelItem.Initial, self.node1.get_state())

        remove_prop_operation.mutate_backward(self.model)
        self.assertTrue("prop2" in self.node1.properties)
        self.assertEquals("123", self.node1.prop2)
        self.assertEqual(ModelItem.Initial, self.node1.get_state())

    def test_rename_property_operation(self):
        self.assertEqual(ModelItem.Initial, self.node1.get_state())
        rename_prop_operation = RenameProperty("node", "prop2", "prop3")
        rename_prop_operation.mutate_forward(self.model)
        self.assertFalse("prop2" in self.node1.properties)
        self.assertTrue("prop3" in self.node1.properties)
        self.assertEquals("def", self.node1.prop3)
        self.assertEquals(None, self.node1.prop2)
        self.assertEqual(ModelItem.Initial, self.node1.get_state())

        rename_prop_operation.mutate_backward(self.model)
        self.assertFalse("prop3" in self.node1.properties)
        self.assertTrue("prop2" in self.node1.properties)
        self.assertEquals("def", self.node1.prop2)
        self.assertEqual(ModelItem.Initial, self.node1.get_state())

    def test_rename_property_operation_applied_state(self):
        rename_prop_operation = RenameProperty("node", "prop2", "prop3")
        self._assert_state_transition(
                self.node1, ModelItem.Applied, rename_prop_operation, ModelItem.Updated)

    def test_rename_property_operation_for_removal_state(self):
        rename_prop_operation = RenameProperty("node", "prop2", "prop3")
        self._assert_state_transition(
                self.node1, ModelItem.ForRemoval, rename_prop_operation, ModelItem.Updated)

    def test_rename_property_operation_updated_state(self):
        rename_prop_operation = RenameProperty("node", "prop2", "prop3")
        self._assert_state_transition(
                self.node1, ModelItem.Updated, rename_prop_operation, ModelItem.Updated)

    def test_rename_property_operation_invalid_prop(self):
        self.assertEqual(ModelItem.Initial, self.node1.get_state())
        self.assertFalse("bad_prop" in self.node1.properties)
        rename_prop_operation = RenameProperty("node", "bad_prop", "prop3")
        self.assertRaises(ValueError, rename_prop_operation.mutate_forward, self.model)
        self.assertTrue("prop2" in self.node1.properties)
        self.assertFalse("prop3" in self.node1.properties)
        self.assertEqual(ModelItem.Initial, self.node1.get_state())

    def test_rename_property_operation_invalid_prop_applied_state(self):
        self.node1.set_applied()
        rename_prop_operation = RenameProperty("node", "bad_prop", "prop3")
        self.assertRaises(ValueError, rename_prop_operation.mutate_forward, self.model)
        self.assertEqual(ModelItem.Applied, self.node1.get_state())

    def test_rename_property_operation_invalid_prop_applied_state(self):
        self.node1.set_for_removal()
        rename_prop_operation = RenameProperty("node", "bad_prop", "prop3")
        self.assertRaises(ValueError, rename_prop_operation.mutate_forward, self.model)
        self.assertEqual(ModelItem.ForRemoval, self.node1.get_state())

    def test_rename_property_operation_invalid_prop_updated_state(self):
        self.node1.set_updated()
        rename_prop_operation = RenameProperty("node", "bad_prop", "prop3")
        self.assertRaises(ValueError, rename_prop_operation.mutate_forward, self.model)
        self.assertEqual(ModelItem.Updated, self.node1.get_state())

    def test_rename_item_type_operation(self):
        rename_item_type_operation = RenameItemType("node", "new-node")
        self.assertEquals("node", self.node1._item_type.item_type_id)
        rename_item_type_operation.mutate_forward(self.model)
        self.node1 = self.model.get_item(self.node1.vpath)
        self.assertEquals("new-node", self.node1._item_type.item_type_id)
        rename_item_type_operation.mutate_backward(self.model)
        self.node1 = self.model.get_item(self.node1.vpath)
        self.assertEquals("node", self.node1._item_type.item_type_id)

    def test_update_collection_type_operation(self):
        nodes = self.model.get_item("/nodes")
        self.assertEquals("node", nodes._item_type.item_type_id)
        node1 = self.model.get_item("/nodes/node1")
        self.assertEquals("node", node1._item_type.item_type_id)

        # Migrating an empty collection is OK
        self.model.remove_item('/nodes/node1')
        operation = UpdateCollectionType("root", "nodes", "node", "new-node")

        operation.mutate_forward(self.model)
        nodes = self.model.get_item("/nodes")
        self.assertEquals("new-node", nodes._item_type.item_type_id)

        operation.mutate_backward(self.model)
        nodes = self.model.get_item("/nodes")
        self.assertEquals("node", nodes._item_type.item_type_id)

        # Migrating a non-empty collection can only be done if we're migrating
        # to a supertype
        self.node1 = self.model.create_item("node", "/nodes/node1",
                                            prop1="abc", prop2="def")

        operation = UpdateCollectionType("root", "nodes", "node", "node-base")

        operation.mutate_forward(self.model)
        nodes = self.model.get_item("/nodes")
        self.assertEquals("node-base", nodes._item_type.item_type_id)

        operation.mutate_backward(self.model)
        nodes = self.model.get_item("/nodes")
        self.assertEquals("node", nodes._item_type.item_type_id)
