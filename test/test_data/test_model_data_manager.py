import unittest

from mock import patch
from litp.data.db_storage import DbStorage
from litp.data.data_manager import DataManager
from litp.data.base_model_data_manager import BaseModelDataManager
from litp.data.model_data_manager import ModelDataManager
from litp.core.model_manager import ModelManager
from litp.core.model_type import ItemType
from litp.core.model_type import Child
from litp.core.model_item import ModelItem
from litp.core.model_item import CollectionItem
from litp.core.model_item import RefCollectionItem
from litp.core.extension_info import ExtensionInfo

from litp.data.test_db_engine import get_engine


class TestBaseModelDataManager(unittest.TestCase):
    def __init__(self, *args, **kwargs):
        super(TestBaseModelDataManager, self).__init__(*args, **kwargs)
        self.storage = DbStorage(get_engine())
        self.storage.reset()
        self._patcher = patch(
            "litp.data.data_manager.ModelDataManager", new=BaseModelDataManager)

    def _create_managers(self):
        model_manager = ModelManager()
        model_manager.register_item_types([
            ItemType(
                "root",
                foo=Child("foo"),
                bar=Child("bar")
            ),
            ItemType(
                "foo",
                baz=Child("baz")
            ),
            ItemType(
                "bar",
                baz=Child("baz")
            ),
            ItemType(
                "baz"
            )
        ])

        session = self.storage.create_session()
        data_manager = DataManager(session)
        data_manager.configure(model_manager)
        model_manager._data_manager = data_manager
        self._data_managers.append(data_manager)
        return (data_manager, model_manager)

    def setUp(self):
        self._patcher.start()
        self._data_managers = []
        self.data_manager, self.model_manager = self._create_managers()

    def tearDown(self):
        for data_manager in self._data_managers:
            data_manager.rollback()
            data_manager.close()
        self.storage.reset()
        self._patcher.stop()

    def test_model_item(self):
        data_manager1, model_manager1 = self._create_managers()
        item1 = ModelItem(model_manager1, model_manager1.item_types["foo"], "foo", "/")
        item1.source_vpath = "/bar"
        item1.state = ModelItem.Updated
        item1.previous_state = ModelItem.Applied
        item1.properties.update({"x": "X", "y": "Y"})
        item1.applied_properties.update({"x": "XX", "y": "YY"})
        item1.applied_properties_determinable = False
        data_manager1.model.add(item1)
        data_manager1.commit()

        data_manager2, model_manager2 = self._create_managers()
        item2 = data_manager2.model.get("/foo")
        self.assertTrue(item2 is not None)

        self.assertEquals("/foo", item1.vpath)
        self.assertEquals(item1.vpath, item2.vpath)
        self.assertEquals("foo", item1.item_id)
        self.assertEquals(item1.item_type_id, item2.item_type_id)
        self.assertEquals("foo", item1.item_type_id)
        self.assertEquals(item1.item_type_id, item2.item_type_id)
        self.assertEquals("/", item1.parent_vpath)
        self.assertEquals(item1.parent_vpath, item2.parent_vpath)
        self.assertEquals("/bar", item1.source_vpath)
        self.assertEquals(item1.source_vpath, item2.source_vpath)
        self.assertEquals(ModelItem.Updated, item1.state)
        self.assertEquals(item1.state, item2.state)
        self.assertEquals(ModelItem.Applied, item1.previous_state)
        self.assertEquals(item1.previous_state, item2.previous_state)
        self.assertEquals({"x": "X", "y": "Y"}, item1.properties)
        self.assertEquals(item1.properties, item2.properties)
        self.assertEquals({"x": "XX", "y": "YY"}, item1.applied_properties)
        self.assertEquals(item1.applied_properties, item2.applied_properties)
        self.assertEquals(False, item1.applied_properties_determinable)
        self.assertEquals(item1.applied_properties_determinable, item2.applied_properties_determinable)

    #def delete_model_snapshot_sets(self, exclude_snapshots):

    def test_delete_model_snapshot_sets(self):
        item = ModelItem(self.model_manager, self.model_manager.item_types["root"], "", None)
        self.data_manager.model.add(item)
        item = ModelItem(self.model_manager, self.model_manager.item_types["foo"], "foo", "/")
        item._properties["name"] = "bar"
        self.data_manager.model.add(item)

        extension1 = ExtensionInfo("name", "classpath", "version")
        self.data_manager.add_extension(extension1)
        self.data_manager.commit()

        self.assertFalse(self.data_manager.model.backup_exists("SNAPSHOT_test"))
        self.data_manager.model.create_backup("SNAPSHOT_test")
        self.assertTrue(self.data_manager.model.backup_exists("SNAPSHOT_test"))
        self.data_manager.model.delete_snapshot_sets([])
        self.assertFalse(self.data_manager.model.backup_exists("SNAPSHOT_test"))

    def test_delete_model_snapshot_sets_exclude(self):
        item = ModelItem(self.model_manager, self.model_manager.item_types["root"], "", None)
        self.data_manager.model.add(item)
        item = ModelItem(self.model_manager, self.model_manager.item_types["foo"], "foo", "/")
        item._properties["name"] = "bar"
        self.data_manager.model.add(item)

        snapshot_item = ModelItem(self.model_manager, self.model_manager.item_types["foo"], "test", "/")

        extension1 = ExtensionInfo("name", "classpath", "version")
        self.data_manager.add_extension(extension1)
        self.data_manager.commit()

        self.assertFalse(self.data_manager.model.backup_exists("SNAPSHOT_test"))
        self.assertFalse(self.data_manager.model.backup_exists("SNAPSHOT_test1"))

        self.data_manager.model.create_backup("SNAPSHOT_test")
        self.data_manager.model.create_backup("SNAPSHOT_test1")

        self.assertTrue(self.data_manager.model.backup_exists("SNAPSHOT_test"))
        self.assertTrue(self.data_manager.model.backup_exists("SNAPSHOT_test1"))
        self.data_manager.model.delete_snapshot_sets([snapshot_item])
        self.assertTrue(self.data_manager.model.backup_exists("SNAPSHOT_test"))
        self.assertFalse(self.data_manager.model.backup_exists("SNAPSHOT_test1"))

    def test_create_restore_backup(self):
        item = ModelItem(self.model_manager, self.model_manager.item_types["root"], "", None)
        self.data_manager.model.add(item)
        item = ModelItem(self.model_manager, self.model_manager.item_types["foo"], "foo", "/")
        item._properties["name"] = "bar"
        self.data_manager.model.add(item)
        extension1 = ExtensionInfo("name", "classpath", "version")
        self.data_manager.add_extension(extension1)
        self.data_manager.commit()

        self.assertFalse(self.data_manager.model.backup_exists("test"))

        self.data_manager.model.create_backup("test")

        self.assertTrue(self.data_manager.model.backup_exists("test"))

        item = self.data_manager.model.get("/foo")
        item._properties["name"] = "baz"

        self.data_manager.model.restore_backup("test")

        item = self.data_manager.model.get("/foo")
        self.assertEquals("bar", item._properties["name"])
        vpaths = [item.vpath for item in self.data_manager.model.query()]
        self.assertEquals(set(["/", "/foo"]), set(vpaths))

    def test_restore_backup_exclude(self):
        item = ModelItem(self.model_manager, self.model_manager.item_types["root"], "", None)
        self.data_manager.model.add(item)

        item = ModelItem(self.model_manager, self.model_manager.item_types["foo"], "foo", "/")
        self.data_manager.model.add(item)
        item._properties["name"] = "v1"

        item = ModelItem(self.model_manager, self.model_manager.item_types["bar"], "bar", "/")
        self.data_manager.model.add(item)
        item._properties["name"] = "v1"

        item = ModelItem(self.model_manager, self.model_manager.item_types["baz"], "baz", "/bar")
        self.data_manager.model.add(item)
        item._properties["name"] = "v1"

        self.data_manager.model.create_backup("test")

        item = self.data_manager.model.get("/foo")
        item._properties["name"] = "v2"

        item = self.data_manager.model.get("/bar")
        item._properties["name"] = "v2"

        item = self.data_manager.model.get("/bar/baz")
        item._properties["name"] = "v2"

        # Pass multiple items to exclude set - exclude all items
        self.data_manager.model.restore_backup("test", exclude=set(["/bar", "/foo"]))

        bar = self.data_manager.model.get("/bar")
        self.assertEquals("v2", bar._properties["name"])

        baz = self.data_manager.model.get("/bar/baz")
        self.assertEquals("v2", baz._properties["name"])

        foo = self.data_manager.model.get("/foo")
        self.assertEquals("v2", foo._properties["name"])

        self.data_manager.model.restore_backup("test", exclude=set(["/bar"]))

        item = self.data_manager.model.get("/foo")
        self.assertEquals("v1", item._properties["name"])

        item = self.data_manager.model.get("/bar")
        self.assertEquals("v2", item._properties["name"])

        item = self.data_manager.model.get("/bar/baz")
        self.assertEquals("v2", item._properties["name"])

        self.data_manager.model.restore_backup("test", exclude=set(["/bar/"]))

        item = self.data_manager.model.get("/foo")
        self.assertEquals("v1", item._properties["name"])

        item = self.data_manager.model.get("/bar")
        self.assertEquals("v1", item._properties["name"])

        item = self.data_manager.model.get("/bar/baz")
        self.assertEquals("v2", item._properties["name"])

    def test_basics(self):
        self.assertEquals(
            set([]),
            set([item for item in self.data_manager.model.query()])
        )

        self.assertFalse(self.data_manager.model.exists("/"))
        root_item = ModelItem(self.model_manager, self.model_manager.item_types["root"], "", None, {})
        self.data_manager.model.add(root_item)
        self.assertTrue(self.data_manager.model.exists("/"))
        self.assertEquals(root_item, self.data_manager.model.get("/"))

        self.assertFalse(self.data_manager.model.exists("/foo"))
        foo_item = CollectionItem(self.model_manager, self.model_manager.item_types["foo"], "foo", "/", {})
        self.data_manager.model.add(foo_item)
        self.assertTrue(self.data_manager.model.exists("/foo"))
        self.assertEquals(foo_item, self.data_manager.model.get("/foo"))

        self.assertFalse(self.data_manager.model.exists("/bar"))
        bar_item = RefCollectionItem(self.model_manager, self.model_manager.item_types["bar"], "bar", "/", {})
        self.data_manager.model.add(bar_item)
        self.assertTrue(self.data_manager.model.exists("/bar"))
        self.assertEquals(bar_item, self.data_manager.model.get("/bar"))

        self.assertFalse(self.data_manager.model.exists("/foo/baz"))
        foo_child_item = ModelItem(self.model_manager, self.model_manager.item_types["baz"], "baz", "/foo", {})
        self.data_manager.model.add(foo_child_item)
        self.assertTrue(self.data_manager.model.exists("/foo/baz"))
        self.assertEquals(foo_child_item, self.data_manager.model.get("/foo/baz"))

        self.assertFalse(self.data_manager.model.exists("/bar/baz"))
        bar_child_item = ModelItem(self.model_manager, self.model_manager.item_types["baz"], "baz", "/bar", {})
        self.data_manager.model.add(bar_child_item)
        self.assertTrue(self.data_manager.model.exists("/bar/baz"))
        self.assertEquals(bar_child_item, self.data_manager.model.get("/bar/baz"))

        self.assertEquals(
            set([root_item, foo_item, foo_child_item, bar_item, bar_child_item]),
            set(self.data_manager.model.query())
        )

        self.assertEquals(
            set([foo_item, foo_child_item, bar_item, bar_child_item]),
            set(self.data_manager.model.query_descends(root_item))
        )
        self.assertEquals(
            2,
            self.data_manager.model.count_children(root_item)
        )
        self.assertEquals(
            set([foo_item, bar_item]),
            set(self.data_manager.model.query_children(root_item))
        )

        self.assertEquals(
            set([foo_child_item]),
            set(self.data_manager.model.query_descends(foo_item))
        )
        self.assertEquals(
            1,
            self.data_manager.model.count_children(foo_item)
        )
        self.assertEquals(
            set([foo_child_item]),
            set(self.data_manager.model.query_children(foo_item))
        )

        self.assertEquals(
            set([]),
            set(self.data_manager.model.query_descends(bar_child_item))
        )
        self.assertEquals(
            0,
            self.data_manager.model.count_children(bar_child_item)
        )
        self.assertEquals(
            set([]),
            set(self.data_manager.model.query_children(bar_child_item))
        )

        item = self.data_manager.model.get("/foo/baz")
        self.data_manager.model.delete(item)
        self.assertFalse(self.data_manager.model.exists("/foo/baz"))
        self.assertEquals(
            set([root_item, foo_item, bar_item, bar_child_item]),
            set(self.data_manager.model.query())
        )

        item = self.data_manager.model.get("/foo")
        self.data_manager.model.delete(item)
        self.assertFalse(self.data_manager.model.exists("/foo"))
        self.assertEquals(
            set([root_item, bar_item, bar_child_item]),
            set(self.data_manager.model.query())
        )

        self.data_manager.commit()


class TestModelDataManager(TestBaseModelDataManager):
    def __init__(self, *args, **kwargs):
        super(TestModelDataManager, self).__init__(*args, **kwargs)
        self._patcher = patch(
            "litp.data.data_manager.ModelDataManager", new=ModelDataManager)

    def test_model_item_registration(self):
        item = ModelItem(self.model_manager, self.model_manager.item_types["root"], "", None, {})

        self.data_manager.model.add(item)
        self.assertTrue(self.data_manager.model in item.model_data_manager_instances)

        self.data_manager.model.invalidate_cache()
        self.assertFalse(self.data_manager.model in item.model_data_manager_instances)

        self.data_manager.model.get("/")
        self.assertTrue(self.data_manager.model in item.model_data_manager_instances)
