import unittest

from litp.data.model_cache import IndexValues
from litp.data.model_cache import Index
from litp.data.model_cache import ModelCache

from litp.data.db_storage import DbStorage
from litp.data.data_manager import DataManager
from litp.core.model_manager import ModelManager
from litp.core.model_type import ItemType
from litp.core.model_type import Child
from litp.core.model_item import ModelItem
from litp.core.model_item import CollectionItem
from litp.core.model_item import RefCollectionItem
from litp.data.test_db_engine import get_engine


class TestIndexValues(unittest.TestCase):
    def test_empty(self):
        iv = IndexValues()
        self.assertEquals(0, len(iv))
        self.assertEquals([], iv.values())

    def test_add(self):
        iv = IndexValues()

        iv.add("foo")
        self.assertEquals(1, len(iv))
        self.assertEquals(["foo"], iv.values())

        iv.add("bar")
        self.assertEquals(2, len(iv))
        self.assertEquals(["bar", "foo"], iv.values())

    def test_remove(self):
        iv = IndexValues()

        iv.add("foo")
        iv.remove("foo")
        self.assertEquals(0, len(iv))
        self.assertEquals([], iv.values())


class TestIndex(unittest.TestCase):
    def test_empty(self):
        items = {}
        fn_key = lambda x: x["value"]
        fn_value = lambda x: x["key"]
        fn_item_lookup = lambda x: items[x]

        index = Index(fn_key, fn_value, fn_item_lookup)
        self.assertEquals(0, index.count("foo"))
        self.assertEquals(0, len(list(index.itervalues("foo"))))

    def test_add(self):
        items = {}
        fn_key = lambda x: x["value"]
        fn_value = lambda x: x["key"]
        fn_item_lookup = lambda x: items[x]

        index = Index(fn_key, fn_value, fn_item_lookup)

        item1 = {
            "key": "foo",
            "value": "foo_val"
        }
        item2 = {
            "key": "bar",
            "value": "foo_val"
        }
        item3 = {
            "key": "baz",
            "value": "baz_val"
        }

        items[item1["key"]] = item1
        items[item2["key"]] = item2
        items[item3["key"]] = item3

        index.add(item1)
        index.add(item2)
        index.add(item3)

        self.assertEquals(2, index.count("foo_val"))
        self.assertEquals([item2, item1], list(index.itervalues("foo_val")))

        self.assertEquals(1, index.count("baz_val"))
        self.assertEquals([item3], list(index.itervalues("baz_val")))

    def test_remove(self):
        items = {}
        fn_key = lambda x: x["value"]
        fn_value = lambda x: x["key"]
        fn_item_lookup = lambda x: items[x]

        index = Index(fn_key, fn_value, fn_item_lookup)

        item1 = {
            "key": "foo",
            "value": "foo_val"
        }
        item2 = {
            "key": "bar",
            "value": "foo_val"
        }
        item3 = {
            "key": "baz",
            "value": "baz_val"
        }

        items[item1["key"]] = item1
        items[item2["key"]] = item2
        items[item3["key"]] = item3

        index.add(item1)
        index.add(item2)
        index.add(item3)

        index.remove(item2)
        index.remove(item3)

        self.assertEquals(1, index.count("foo_val"))
        self.assertEquals([item1], list(index.itervalues("foo_val")))

        self.assertEquals(0, index.count("baz_val"))
        self.assertEquals([], list(index.itervalues("baz_val")))

    def test_update(self):
        items = {}
        fn_key = lambda x: x["value"]
        fn_value = lambda x: x["key"]
        fn_item_lookup = lambda x: items[x]

        index = Index(fn_key, fn_value, fn_item_lookup)

        item = {
            "key": "foo",
            "value": "foo_val"
        }
        items[item["key"]] = item
        index.add(item)

        index.update(item, "foo_val", "baz_val")

        self.assertEquals(0, index.count("foo_val"))
        self.assertEquals([], list(index.itervalues("foo_val")))

        self.assertEquals(1, index.count("baz_val"))
        self.assertEquals([item], list(index.itervalues("baz_val")))


class TestModelCache(unittest.TestCase):
    def __init__(self, *args, **kwargs):
        super(TestModelCache, self).__init__(*args, **kwargs)
        self.storage = DbStorage(get_engine())
        self.storage.reset()

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
        data_manager.configure_model_cache()
        return (data_manager, model_manager)

    def setUp(self):
        self._data_managers = []
        self.data_manager, self.model_manager = self._create_managers()

    def tearDown(self):
        for data_manager in self._data_managers:
            data_manager.rollback()
            data_manager.close()
        self.storage.reset()

    def test_index_update(self):
        data_manager1, model_manager1 = self._create_managers()

        item1 = ModelItem(model_manager1, model_manager1.item_types["foo"], "foo", "/")
        item1.source_vpath = "/bar"
        item1.state = ModelItem.Updated
        item1.previous_state = ModelItem.Applied
        data_manager1.model.add(item1)

        items = list(data_manager1.model.query_by_states(set([ModelItem.Applied])))
        self.assertEquals([], [item._vpath for item in items])

        items = list(data_manager1.model.query_by_states(set([ModelItem.Updated])))
        self.assertEquals([item1._vpath], [item._vpath for item in items])

        item1._state = ModelItem.Applied

        items = list(data_manager1.model.query_by_states(set([ModelItem.Updated])))
        self.assertEquals([], [item._vpath for item in items])

        items = list(data_manager1.model.query_by_states(set([ModelItem.Applied])))
        self.assertEquals([item1._vpath], [item._vpath for item in items])

        data_manager1.model.delete(item1)

    def test_model_item_registration(self):
        item = ModelItem(self.model_manager, self.model_manager.item_types["root"], "", None, {})

        self.data_manager.model.add(item)
        self.assertTrue(self.data_manager.model in item.model_cache_instances)

        self.data_manager.model.invalidate_cache()
        self.assertFalse(self.data_manager.model in item.model_cache_instances)
