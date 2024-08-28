from litp.core.model_manager import ModelManager
from litp.core.model_type import PropertyType, ItemType, Collection, Property
from litp.migration import BaseMigration
from litp.migration.operations import AddProperty, RemoveProperty, \
                                      RenameProperty
import unittest


class MockMigration1(BaseMigration):
    version = '1.2.4'
    operations = [
        AddProperty('node', 'prop3', 'ghi'),
    ]


class MockMigration2(BaseMigration):
    version = '1.2.4'
    operations = [
        RemoveProperty('node', 'prop1', '123'),
    ]


class MockMigration3(BaseMigration):
    version = '1.2.4'
    operations = [
        AddProperty('node', 'prop1', 'ghi'),
        RemoveProperty('node', 'prop2', 'ghi'),
        RenameProperty('node', 'prop3', 'prop4'),
    ]


class MockMigration4(BaseMigration):
    version = '1.2.4'
    operations = [
        AddProperty('node', "is_locked", "true"),
    ]


class MockMigration_add_invalid(BaseMigration):
    version = '1.2.4'
    operations = [
        AddProperty('node', 'prop_invalid', 'ghi_invalid'),
    ]


class MockMigration_remove_invalid(BaseMigration):
    version = '1.2.4'
    operations = [
        RemoveProperty('node', 'prop_invalid', '123_invalid'),
    ]


class TestMigration(unittest.TestCase):

    def setUp(self):
        self.model = ModelManager()
        self.model.register_property_type(PropertyType("basic_string"))
        self.model.register_property_type(PropertyType("basic_boolean", regex=r"^(true|false)$"))
        self.model.register_item_type(ItemType("node",
                                               prop1=Property("basic_string"),
                                               prop2=Property("basic_string"),
                                               prop3=Property("basic_string"),
                                               prop4=Property("basic_string"),
                                               is_locked=Property("basic_boolean",
                                                    default="false",
                                                    prop_description="Set to true if this node is locked.",
                                                    required=True,
                                                    updatable_rest=False,
                                                    updatable_plugin=False,
                                                               )
                                               )
                                      )
        self.model.register_item_type(ItemType("root",
                                               nodes=Collection("node")
                                               )
                                      )
        self.model.create_root_item("root")
        self.node1 = self.model.create_item("node", "/nodes/node1",
                                            prop1="abc", prop2="def")
        self.migration1 = BaseMigration()
        self.migration2 = BaseMigration()

    def test_migration_adding_property(self):
        migration = MockMigration1()
        migration.forwards(self.model)
        self.node1 = self.model.get_item(self.node1.vpath)
        self.assertTrue("prop3" in self.node1.properties)
        self.assertEquals("ghi", self.node1.prop3)
        migration.backwards(self.model)
        self.node1 = self.model.get_item(self.node1.vpath)
        self.assertTrue("prop3" not in self.node1.properties)

    def test_migration_removing_property(self):
        migration = MockMigration2()
        migration.forwards(self.model)
        self.node1 = self.model.get_item(self.node1.vpath)
        self.assertTrue("prop1" not in self.node1.properties)
        migration.backwards(self.model)
        self.node1 = self.model.get_item(self.node1.vpath)
        self.assertTrue("prop1" in self.node1.properties)
        self.assertEquals("123", self.node1.prop1)

    def test_migration_multiple_property_operations(self):
        migration = MockMigration3()
        self.node1.set_property("prop2", "asdf2")
        self.node1.set_property("prop3", "asdf3")

        migration.forwards(self.model)
        self.node1 = self.model.get_item(self.node1.vpath)
        self.assertTrue("prop1" in self.node1.properties)
        self.assertEquals("ghi", self.node1.prop1)
        self.assertTrue("prop2" not in self.node1.properties)
        self.assertTrue("prop3" not in self.node1.properties)
        self.assertTrue("prop4" in self.node1.properties)
        self.assertEquals("asdf3", self.node1.prop4)

        migration.backwards(self.model)
        self.node1 = self.model.get_item(self.node1.vpath)
        self.assertTrue("prop1" not in self.node1.properties)
        self.assertTrue("prop2" in self.node1.properties)
        self.assertEquals("ghi", self.node1.prop2)
        self.assertTrue("prop4" not in self.node1.properties)
        self.assertTrue("prop3" in self.node1.properties)
        self.assertEquals("asdf3", self.node1.prop3)

    def test_migration_normalized_version(self):
        self.assertEquals([0, 0, 0, 0],  self.migration1.normalized_version)
        self.migration1.version = "1.2.3"
        self.assertEquals([1, 2, 3, 0],  self.migration1.normalized_version)
        self.migration1.version = "1.2"
        self.assertEquals([1, 2, 0, 0],  self.migration1.normalized_version)
        self.migration1.version = "1.0.123-SNAPSHOT123"
        self.assertEquals([1, 0, 123, 0],  self.migration1.normalized_version)
        self.migration1.version = "a.b.c"
        self.assertEquals(['a', 'b', 'c', 0],
                          self.migration1.normalized_version)

    def test_migration_compare_greater_than(self):
        self.migration1.version = "1.2.45"
        self.migration2.version = "1.2.3"
        self.assertTrue(self.migration1 > self.migration2)
        self.migration1.version = "1.3"
        self.migration2.version = "1.2.3"
        self.assertTrue(self.migration1 > self.migration2)

    def test_migration_compare_less_than(self):
        self.migration1.version = "1.2"
        self.migration2.version = "1.2.3"
        self.assertTrue(self.migration1 < self.migration2)
        self.migration1.version = "1.2.2"
        self.migration2.version = "1.2.45"
        self.assertTrue(self.migration1 < self.migration2)

    def test_migration_compare_equal(self):
        self.migration1.version = "1.2"
        self.migration2.version = "1.2.0"
        self.assertTrue(self.migration1 == self.migration2)
        self.migration1.version = "1"
        self.migration2.version = "1.0.0"
        self.assertTrue(self.migration1 == self.migration2)

    def test_migration_of_is_locked(self):
        self.assertEquals("false", self.node1.is_locked)
        migration = MockMigration4()
        migration.forwards(self.model)
        self.node1 = self.model.get_item(self.node1.vpath)
        self.assertEquals("true", self.node1.is_locked)
        self.assertEquals(False, self.model.get_item("/nodes/node1")._item_type.structure["is_locked"].updatable_rest)
        self.assertEquals(False, self.model.get_item("/nodes/node1")._item_type.structure["is_locked"].updatable_plugin)
        self.assertEquals(True, self.model.get_item("/nodes/node1")._item_type.structure["is_locked"].required)

        # This unsets the is_locked property from the item. However, since the
        # property is required and has a default value, the property will
        # effectively be reset to its default value
        migration.backwards(self.model)
        self.node1 = self.model.get_item(self.node1.vpath)
        self.assertTrue('is_locked' in self.node1.properties)
        self.assertEquals('false', self.node1.is_locked)

        # This removes the is_locked prop from the item type structure,
        # simulating a backwards-incompatible model extension change
        del self.model.item_types['node'].structure['is_locked']
        self.node1.delete_property('is_locked')

        self.assertTrue('is_locked' not in self.node1.properties)
        self.assertRaises(AttributeError, getattr, self.node1, 'is_locked')

    def test_migration_add_invalid_property(self):
        migration = MockMigration_add_invalid()
        migration.backwards(self.model)
        self.assertRaises(ValueError, lambda: migration.forwards(self.model))

    def test_migration_remove_invalid_property(self):
        migration = MockMigration_remove_invalid()
        migration.forwards(self.model)
        self.assertRaises(ValueError, lambda: migration.backwards(self.model))
