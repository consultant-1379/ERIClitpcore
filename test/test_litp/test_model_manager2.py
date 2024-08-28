import unittest

from litp.core.model_manager import ModelManager, QueryItem
from litp.core.model_item import ModelItem
from litp.core.model_type import ItemType
from litp.core.model_type import Child
from litp.core.model_type import Collection
from litp.core.model_type import Property
from litp.core.model_type import RefCollection
from litp.core.model_type import PropertyType
from litp.core.exceptions import NotModelItemException


class TestModelManager(unittest.TestCase):
    def create_item(self, item_type, item_path, **props):
        result = self.manager.create_item(item_type, item_path, **props)
        if not isinstance(result, ModelItem):
            raise NotModelItemException(result)
        return result

    def update_item(self, item_path, **props):
        result = self.manager.update_item(item_path, **props)
        if not isinstance(result, ModelItem):
            raise NotModelItemException(result)
        return result

    def remove_item(self, item_path):
        result = self.manager.remove_item(item_path)
        if not isinstance(result, ModelItem):
            raise NotModelItemException(result)
        return result

    def create_inherited(self, source_item_path, item_path, **props):
        result = self.manager.create_inherited(source_item_path, item_path, **props)
        if not isinstance(result, ModelItem):
            raise NotModelItemException(result)
        return result

    def setUp(self):
        self.manager = ModelManager()

        self.manager.register_property_types([
            PropertyType("basic_string")
        ])

        self.manager.register_item_types([
            ItemType(
                "root",
                foo=Child("foo"),
                bar=Child("bar", require="foo")
            ),
            ItemType(
                "item",
                name=Property("basic_string", required=True),
                description=Property("basic_string", default="default description"),
                comment=Property("basic_string"),
                other1=Child("other", required=True),
                other2=Child("other")
            ),
            ItemType(
                "other",
                description=Property("basic_string", default="default description for other")
            ),
            ItemType(
                "foo",
                items=Collection("item")
            ),
            ItemType(
                "bar",
                items=RefCollection("item")
            )
        ])

        self.root = self.manager.create_root_item("root")

    def test_create_under_item_mfr(self):
        self.create_item("foo", "/foo")
        self.manager.set_all_applied()
        self.remove_item("/foo")

        self.assertEqual(ModelItem.ForRemoval, self.manager.get_item("/foo").get_state())
        self.assertEqual(ModelItem.ForRemoval, self.manager.get_item("/foo/items").get_state())

        self.assertRaises(NotModelItemException, self.create_item, "item", "/foo/items/item1", name="item1")

    def test_recover_create_under_item_mfr(self):
        self.create_item("foo", "/foo")
        self.create_item("item", "/foo/items/item1", name="item1")
        self.manager.set_all_applied()
        self.remove_item("/foo")

        self.assertEqual(ModelItem.ForRemoval, self.manager.get_item("/foo").get_state())
        self.assertEqual(ModelItem.ForRemoval, self.manager.get_item("/foo/items").get_state())
        self.assertEqual(ModelItem.ForRemoval, self.manager.get_item("/foo/items/item1").get_state())

        self.assertRaises(NotModelItemException, self.create_item, "item", "/foo/items/item1", name="item1")

    def test_recover_update_under_item_mfr(self):
        self.create_item("foo", "/foo")
        self.create_item("item", "/foo/items/item1", name="item1")
        self.manager.set_all_applied()
        self.remove_item("/foo")

        self.assertEqual(ModelItem.ForRemoval, self.manager.get_item("/foo").get_state())
        self.assertEqual(ModelItem.ForRemoval, self.manager.get_item("/foo/items").get_state())
        self.assertEqual(ModelItem.ForRemoval, self.manager.get_item("/foo/items/item1").get_state())

        self.assertRaises(NotModelItemException, self.update_item, "/foo/items/item1", name="item1")

    def test_recover_inherit_under_item_mfr(self):
        self.create_item("foo", "/foo")
        self.create_item("item", "/foo/items/item1", name="item1")
        self.create_item("bar", "/bar")
        self.create_inherited("/foo/items/item1", "/bar/items/item1")
        self.manager.set_all_applied()
        self.remove_item("/bar")

        self.assertEqual(ModelItem.ForRemoval, self.manager.get_item("/bar").get_state())
        self.assertEqual(ModelItem.ForRemoval, self.manager.get_item("/bar/items").get_state())
        self.assertEqual(ModelItem.ForRemoval, self.manager.get_item("/bar/items/item1").get_state())

        self.assertRaises(NotModelItemException, self.create_inherited, "/foo/items/item1", "/bar/items/item1")

    def test_applied_properties_inherit(self):
        self.create_item("foo", "/foo")
        self.create_item("bar", "/bar")
        self.create_item("item", "/foo/items/source", name="alpha")

        self.create_inherited("/foo/items/source", "/bar/items/dest")
        src = QueryItem(self.manager,
                self.manager.query_by_vpath("/foo/items/source"))
        dst = QueryItem(self.manager,
                self.manager.query_by_vpath("/bar/items/dest"))

        expected_properties = {
                'name': 'alpha',
                'description': 'default description'
        }
        self.assertTrue(isinstance(src, QueryItem))
        self.assertTrue(src.is_initial())
        self.assertEquals(expected_properties, src.properties)
        self.assertEquals(expected_properties, src._model_item._properties)

        self.assertTrue(isinstance(dst, QueryItem))
        self.assertTrue(dst.is_initial())
        self.assertEquals(expected_properties, dst.properties)
        # No property is overridden from the source
        self.assertEquals({}, dst._model_item._properties)
        self.assertEquals({}, dst.applied_properties)
        self.assertEquals({}, dst._model_item._applied_properties)

        self.manager.set_all_applied()
        self.assertTrue(dst.is_applied())
        self.assertEquals(expected_properties, dst.properties)
        # No property is overridden from the source
        self.assertEquals({}, dst._model_item._properties)
        self.assertEquals(expected_properties, dst.applied_properties)
        self.assertEquals(expected_properties, dst._model_item._applied_properties)
