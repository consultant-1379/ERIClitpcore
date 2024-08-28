import unittest

from litp.core import constants
from litp.core.model_manager import ModelManager
from litp.core.model_type import PropertyType
from litp.core.model_type import ItemType
from litp.core.model_type import Property
from litp.core.model_type import Collection
from litp.core.model_type import RefCollection
from litp.core.model_type import Child
from litp.core.model_type import Reference
from litp.core.model_type import View
from litp.core.model_item import ModelItem
from litp.core.validators import ValidationError


def _view_callable(*args, **kwargs):
    return "view_callable_returned"


def _range_generator(*args, **kwargs):
    raise NotImplementedError


class BaseTest(unittest.TestCase):
    def assertIsNone(self, obj):
        self.assertTrue(obj is None)

    def assertIsNotNone(self, obj):
        self.assertTrue(obj is not None)

    def create_item(self, item_type, item_path, **props):
        result = self.manager.create_item(item_type, item_path, **props)
        if not isinstance(result, ModelItem):
            raise Exception(result)
        return result

    def update_item(self, item_path, **props):
        result = self.manager.update_item(item_path, **props)
        if not isinstance(result, ModelItem):
            raise Exception(result)
        return result

    def remove_item(self, item_path):
        result = self.manager.remove_item(item_path)
        if not isinstance(result, ModelItem):
            raise Exception(result)
        return result

    def create_inherited(self, source_item_path, item_path, **props):
        result = self.manager.create_inherited(source_item_path, item_path, **props)
        if not isinstance(result, ModelItem):
            raise Exception(result)
        return result

    def assertErrorType(self, expected, actual_errors):
        self.assertTrue(isinstance(actual_errors, list), "%s != %s" % (expected, actual_errors))
        self.assertEquals(1, len(actual_errors), "%s != %s" % (expected, actual_errors))
        self.assertEquals(expected, actual_errors[0].error_type)

    def setUp(self):
        self.manager = ModelManager()
        self.manager.register_property_type(
            PropertyType("basic_string")
        )
        self.manager.register_item_type(
            ItemType(
                "ms",
                hostname=Property("basic_string", required=True),
                view=View("basic_string", callable_method=_view_callable)
            )
        )
        self.manager.register_item_type(
            ItemType(
                "fs",
                name=Property("basic_string", required=True, default="default_fs_name"),
                size=Property("basic_string", default="0"),
                description=Property("basic_string"),
                view=View("basic_string", callable_method=_view_callable),
                ref_foo=Reference("foo")
            )
        )
        self.manager.register_item_type(
            ItemType(
                "storage",
                name=Property("basic_string", required=True),
                description=Property("basic_string"),
                filesystems=Collection("fs"),
                view=View("basic_string", callable_method=_view_callable)
            )
        )
        self.manager.register_item_type(
            ItemType(
                "os",
                name=Property("basic_string", required=True)
            )
        )
        self.manager.register_item_type(
            ItemType(
                "node",
                hostname=Property("basic_string", required=True),
                os=Child("os"),
                storage=Reference("storage"),
                storages=RefCollection("storage"),
                fs=Reference("fs"),
                test_config=Child("test_config")
            )
        )
        self.manager.register_item_type(
            ItemType(
                "foo",
                name=Property("basic_string", required=False),
            )
        )
        self.manager.register_item_type(
            ItemType(
                "root",
                foo=Child("foo"),
                test_config=Child("test_config"),
                nodes=Collection("node"),
                ms=Child("ms"),
                storage=Child("storage"),
                filesystems=RefCollection("fs")
            )
        )
        self.manager.register_item_type(
            ItemType(
                "test_config",
                name=Property("basic_string", required=False),
                config=Property("basic_string"),
                non_config=Property("basic_string", configuration=False)
            )
        )
        self.manager.create_root_item("root")
        self.create_item("foo", "/foo")
        self.create_item("test_config", "/test_config", config="config", non_config="non_config")
        self.create_item("ms", "/ms", hostname="ms")
        self.create_item("storage", "/storage", name="storage")
        self.create_item("fs", "/storage/filesystems/root",
                         name="root", size="10")

        self.create_item("node", "/nodes/node1", hostname="node1")
        self.create_item("node", "/nodes/node2", hostname="node2")


class Test(BaseTest):

    def test_create_inherited(self):
        self.create_inherited("/storage", "/nodes/node1/storage", name="storage_inherited")

        storage = self.manager.get_item("/nodes/node1/storage")
        self.assertIsNotNone(storage)
        self.assertIsNotNone(storage.source_vpath)
        self.assertEquals("/storage", storage.source_vpath)
        self.assertTrue(storage.is_initial())
        self.assertEquals("storage_inherited", storage.name)

        fs = self.manager.get_item("/nodes/node1/storage/filesystems/root")
        self.assertIsNotNone(fs)
        self.assertIsNotNone(fs.source_vpath)
        self.assertEquals("/storage/filesystems/root", fs.source_vpath)
        self.assertTrue(fs.is_initial())
        self.assertIsNone(fs.get_property("name"))
        self.assertIsNone(fs.get_property("size"))

    def test_create_inherited_under_refcollection(self):
        self.create_inherited("/storage", "/nodes/node1/storages/s1")

        storage = self.manager.get_item("/nodes/node1/storages/s1")
        self.assertIsNotNone(storage)
        self.assertIsNotNone(storage.source_vpath)

    def test_create_inherited_invalid(self):
        self.assertRaises(Exception,
            self.create_inherited, "/storage/filesystems", "/nodes/node1/fs")

    def test_create_inherited_source_mfr(self):
        self.manager.set_all_applied()
        self.remove_item("/storage")

        result = self.manager.create_inherited("/storage", "/nodes/node1/storage")
        self.assertErrorType(constants.METHOD_NOT_ALLOWED_ERROR, result)

    def test_create_inherited_source_child_mrf(self):
        self.manager.set_all_applied()
        self.remove_item("/storage/filesystems/root")

        self.create_inherited("/storage", "/nodes/node1/storage")

        fs = self.manager.get_item("/nodes/node1/storage/filesystems/root")
        self.assertIsNone(fs)

    ##########

    def test_create_item_under_inherited(self):
        self.create_inherited("/storage", "/nodes/node1/storage")
        result = self.manager.create_item("fs", "/nodes/node1/storage/filesystems/home", name="home", size="20")
        self.assertErrorType(constants.METHOD_NOT_ALLOWED_ERROR, result)

    def test_create_inherited_under_inherited(self):
        self.create_inherited("/storage", "/nodes/node1/storage")
        result = self.manager.create_inherited("/foo", "/nodes/node1/storage/filesystems/root/foo")
        self.assertErrorType(constants.METHOD_NOT_ALLOWED_ERROR, result)

    def test_create_inherited_child_mfr(self):
        self.remove_item("/storage/filesystems/root")
        self.create_inherited("/storage", "/nodes/node1/storage")

        fs = self.manager.get_item("/nodes/node1/storage/filesystems/root")
        self.assertIsNone(fs)

    def test_update_inherited_set_property(self):
        self.create_inherited("/storage", "/nodes/node1/storage")
        self.manager.set_all_applied()

        fs = self.manager.get_item("/nodes/node1/storage/filesystems/root")
        self.assertIsNotNone(fs)
        self.assertIsNone(fs.get_property("name"))
        self.assertIsNone(fs.get_property("size"))

        # updating inherited, same value as in source
        self.update_item("/nodes/node1/storage/filesystems/root", size="10")
        fs = self.manager.get_item("/nodes/node1/storage/filesystems/root")
        self.assertIsNotNone(fs)
        self.assertTrue(fs.is_applied())
        self.assertEquals("10", fs.get_property("size"))

        # updating inherited, different value as in source
        self.update_item("/nodes/node1/storage/filesystems/root", size="100")
        fs = self.manager.get_item("/nodes/node1/storage/filesystems/root")
        self.assertIsNotNone(fs)
        self.assertTrue(fs.is_updated())
        self.assertEquals("100", fs.get_property("size"))

    def test_update_inherited_reset_property(self):
        self.create_inherited("/storage", "/nodes/node1/storage")
        self.update_item("/nodes/node1/storage/filesystems/root", size="100")
        self.manager.set_all_applied()

        self.update_item("/nodes/node1/storage/filesystems/root", size="")

        fs = self.manager.get_item("/nodes/node1/storage/filesystems/root")
        self.assertIsNotNone(fs)
        self.assertTrue(fs.is_updated())
        # LITPCDS-11647: Allow empty sting property values
        self.assertIsNotNone(fs.size)
        self.assertEqual('', fs.size)

    def test_update_inherited_reset_required_property_with_default_value(self):
        self.create_inherited("/storage", "/nodes/node1/storage")
        self.update_item("/nodes/node1/storage/filesystems/root", name="new_name")
        self.manager.set_all_applied()

        self.update_item("/nodes/node1/storage/filesystems/root", name="")

        fs = self.manager.get_item("/nodes/node1/storage/filesystems/root")
        self.assertIsNotNone(fs)
        self.assertTrue(fs.is_updated())
        # LITPCDS-11647: Allow empty sting property values
        self.assertIsNotNone(fs.name)
        self.assertEqual('', fs.name)

    def test_update_inherited_mfr(self):
        self.create_inherited("/storage", "/nodes/node1/storage")
        self.manager.set_all_applied()
        self.remove_item("/nodes/node1/storage")

        fs = self.manager.get_item("/nodes/node1/storage/filesystems/root")
        self.assertIsNotNone(fs)
        self.assertTrue(fs.is_for_removal())

        self.update_item("/nodes/node1/storage")
        storage = self.manager.get_item("/nodes/node1/storage")
        self.assertIsNotNone(storage)
        self.assertTrue(storage.is_applied())

        fs = self.manager.get_item("/nodes/node1/storage/filesystems/root")
        self.assertIsNotNone(fs)
        self.assertTrue(fs.is_applied())

    def test_update_non_config_inherited(self):
        self.manager.create_inherited("/test_config", "/nodes/node1/test_config")
        test = self.manager.get_item("/test_config")
        inherited_test = self.manager.get_item("/nodes/node1/test_config")

        self.manager.update_item("/test_config", non_config="initial")
        self.assertEqual("initial", test.get_property("non_config"))
        self.assertEqual("Initial", test.get_state())
        self.assertEqual("Initial", inherited_test.get_state())

        self.manager.set_all_applied()
        self.manager.update_item("/test_config", non_config="applied")
        self.assertEqual("applied", test.get_property("non_config"))
        self.assertEqual("Applied", test.get_state())
        self.assertEqual("Applied", inherited_test.get_state())

        self.manager.update_item("/test_config", config="updated")
        self.assertEqual("updated", test.get_property("config"))
        self.assertEqual("Updated", test.get_state())
        self.assertEqual("Updated", inherited_test.get_state())

        self.manager.update_item("/test_config", non_config="updated")
        self.assertEqual("updated", test.get_property("non_config"))
        self.assertEqual("Updated", test.get_state())
        self.assertEqual("Updated", inherited_test.get_state())
        self.manager.set_all_applied()

        self.manager.update_item("/nodes/node1/test_config", non_config="inherited")
        self.assertEqual("updated", test.get_property("non_config"))
        self.assertEqual("inherited", inherited_test.get_property("non_config"))
        self.assertEqual("Applied", inherited_test.get_state())

        self.manager.update_item("/test_config", non_config="source")
        self.assertEqual("source", test.get_property("non_config"))
        self.assertEqual("Applied", test.get_state())
        self.assertEqual("inherited", inherited_test.get_property("non_config"))
        self.assertEqual("Applied", inherited_test.get_state())

    def test_update_for_removal_non_config_inherited(self):
        self.manager.create_inherited("/test_config", "/nodes/node1/test_config")
        test = self.manager.get_item("/test_config")
        inherited_test = self.manager.get_item("/nodes/node1/test_config")
        self.manager.set_all_applied()
        self.remove_item("/test_config")

        self.assertEqual("ForRemoval", test.get_state())
        self.assertEqual("ForRemoval", inherited_test.get_state())

        self.manager.update_item("/test_config", non_config="updated")
        self.assertEqual("updated", test.get_property("non_config"))
        self.assertEqual("Applied", test.get_state())
        self.assertEqual("Applied", inherited_test.get_state())

    def test_remove_inherited_initial(self):
        self.create_inherited("/storage", "/nodes/node1/storage")
        self.remove_item("/nodes/node1/storage")

        fs = self.manager.get_item("/nodes/node1/storage/filesystems/root")
        self.assertIsNone(fs)

        storage = self.manager.get_item("/nodes/node1/storage")
        self.assertIsNone(storage)

    def test_remove_inherited_not_initial(self):
        self.create_inherited("/storage", "/nodes/node1/storage")
        self.manager.set_all_applied()

        self.remove_item("/nodes/node1/storage")

        fs = self.manager.get_item("/nodes/node1/storage/filesystems/root")
        self.assertIsNotNone(fs)
        self.assertTrue(fs.is_for_removal())

        storage = self.manager.get_item("/nodes/node1/storage")
        self.assertIsNotNone(storage)
        self.assertTrue(storage.is_for_removal())

    def test_remove_inherited_child(self):
        self.create_inherited("/storage", "/nodes/node1/storage")
        self.manager.set_all_applied()

        # LITPCDS-12018: Allow removal of inherited child item
        inherited_child = self.manager.remove_item("/nodes/node1/storage/filesystems/root")
        self.assertEqual(inherited_child.get_state(), ModelItem.ForRemoval)

    ##########

    def test_create_item_under_source(self):
        self.create_inherited("/storage", "/nodes/node1/storage")
        self.create_item("fs", "/storage/filesystems/home",
                         name="home", size="20")

        fs = self.manager.get_item("/nodes/node1/storage/filesystems/home")
        self.assertIsNotNone(fs)
        self.assertIsNotNone(fs.source_vpath)
        self.assertEquals("/storage/filesystems/home", fs.source_vpath)
        self.assertIsNone(fs.get_property("name"))

    def test_create_inherited_under_source(self):
        self.create_inherited("/storage", "/nodes/node1/storage")
        self.create_inherited("/foo", "/storage/filesystems/root/ref_foo")

        foo = self.manager.get_item("/nodes/node1/storage/filesystems/root/ref_foo")
        self.assertIsNotNone(foo)
        self.assertIsNotNone(foo.source_vpath)
        self.assertEquals("/storage/filesystems/root/ref_foo", foo.source_vpath)

    def test_update_source_property_that_is_not_defined_in_inherited(self):
        self.create_inherited("/storage", "/nodes/node1/storage")
        self.manager.set_all_applied()

        # original value: 10
        self.update_item("/storage/filesystems/root", size="10")

        fs = self.manager.get_item("/nodes/node1/storage/filesystems/root")
        self.assertIsNotNone(fs)
        self.assertIsNone(fs.size)
        self.assertTrue(fs.is_applied())

        self.update_item("/storage/filesystems/root", size="100")

        fs = self.manager.get_item("/nodes/node1/storage/filesystems/root")
        self.assertIsNotNone(fs)
        self.assertIsNone(fs.size)
        self.assertTrue(fs.is_updated())

        self.update_item("/storage/filesystems/root", size="101")

        fs = self.manager.get_item("/nodes/node1/storage/filesystems/root")
        self.assertIsNotNone(fs)
        self.assertIsNone(fs.size)
        self.assertTrue(fs.is_updated())

        # change back to original value: 10
        self.update_item("/storage/filesystems/root", size="10")

        fs = self.manager.get_item("/nodes/node1/storage/filesystems/root")
        self.assertIsNotNone(fs)
        self.assertIsNone(fs.size)
        self.assertTrue(fs.is_applied())

    def test_update_source_property_that_is_defined_in_inherited(self):
        self.create_inherited("/storage", "/nodes/node1/storage")
        self.update_item("/nodes/node1/storage/filesystems/root", size="100")
        self.manager.set_all_applied()

        self.update_item("/storage/filesystems/root", size="1000")

        fs = self.manager.get_item("/nodes/node1/storage/filesystems/root")
        self.assertIsNotNone(fs)
        self.assertTrue(fs.is_applied())

        self.update_item("/storage", name="filesystem_foo")

        fs = self.manager.get_item("/nodes/node1/storage/filesystems/root")
        self.assertIsNotNone(fs)
        self.assertTrue(fs.is_applied())

        st = self.manager.get_item("/nodes/node1/storage")
        self.assertIsNotNone(st)
        self.assertTrue(st.is_updated())

    def test_update_source_property_that_is_defined_in_inherited_two_nodes(self):
        self.create_inherited("/storage", "/nodes/node1/storage")
        self.create_inherited("/storage", "/nodes/node2/storage")
        self.update_item("/nodes/node1/storage/filesystems/root", size="100")
        self.manager.set_all_applied()

        self.update_item("/storage/filesystems/root", size="1000")

        fs_node1 = self.manager.get_item("/nodes/node1/storage/filesystems/root")
        self.assertIsNotNone(fs_node1)
        self.assertIsNotNone(fs_node1.size)
        self.assertTrue(fs_node1.is_applied())

        fs_node2 = self.manager.get_item("/nodes/node2/storage/filesystems/root")
        self.assertIsNotNone(fs_node2)
        self.assertIsNone(fs_node2.size)
        self.assertTrue(fs_node2.is_updated())

        # Change back to original value: 10
        self.update_item("/storage/filesystems/root", size="10")
        fs = self.manager.get_item("/storage/filesystems/root")
        self.assertIsNotNone(fs)
        self.assertIsNotNone(fs.size)
        self.assertTrue(fs.is_applied())

        fs_node1 = self.manager.get_item("/nodes/node1/storage/filesystems/root")
        self.assertIsNotNone(fs_node1)
        self.assertIsNotNone(fs_node1.size)
        self.assertTrue(fs_node1.is_applied())

        fs_node2 = self.manager.get_item("/nodes/node2/storage/filesystems/root")
        self.assertIsNotNone(fs_node2)
        self.assertIsNone(fs_node2.size)
        self.assertTrue(fs_node2.is_applied())

    def test_update_cascaded_inherited(self):
        self.create_inherited("/storage", "/nodes/node1/storages/s1")
        self.create_inherited("/nodes/node1/storages/s1", "/nodes/node1/storages/s2")
        self.manager.set_all_applied()

        self.update_item("/storage/filesystems/root", size="1000")

        s1_fs = self.manager.get_item("/nodes/node1/storages/s1/filesystems/root")
        self.assertIsNotNone(s1_fs)
        self.assertTrue(s1_fs.is_updated())
        s2_fs = self.manager.get_item("/nodes/node1/storages/s2/filesystems/root")
        self.assertIsNotNone(s2_fs)
        self.assertTrue(s2_fs.is_updated())



class TestRecover(BaseTest):
    def setUp(self):
        super(TestRecover, self).setUp()
        self.create_inherited("/storage", "/nodes/node1/storage")
        self.manager.set_all_applied()

        self.remove_item("/nodes/node1/storage")
        node1_storage = self.manager.get_item("/nodes/node1/storage")
        self.assertIsNotNone(node1_storage)
        self.assertTrue(node1_storage.is_for_removal())

        self.remove_item("/storage")
        storage = self.manager.get_item("/storage")
        self.assertIsNotNone(storage)
        self.assertTrue(storage.is_for_removal())

    def test_create_inherited_fails_if_source_mfr(self):
        result = self.manager.create_inherited("/storage", "/nodes/node1/storage")
        self.assertErrorType(constants.METHOD_NOT_ALLOWED_ERROR, result)

    def test_update_inherited_with_same_properties_fails_if_source_mfr(self):
        result = self.manager.update_item("/nodes/node1/storage", name="storage")
        self.assertErrorType(constants.METHOD_NOT_ALLOWED_ERROR, result)

    def test_update_inherited_with_different_properties_fails_if_source_mfr(self):
        result = self.manager.update_item("/nodes/node1/storage", name="storage_x")
        self.assertErrorType(constants.METHOD_NOT_ALLOWED_ERROR, result)


class TestRemove(BaseTest):
    def setUp(self):
        super(TestRemove, self).setUp()
        self.create_inherited("/storage", "/nodes/node1/storage")
        self.create_inherited("/nodes/node1/storage", "/nodes/node2/storage")
        self.create_inherited("/nodes/node2/storage/filesystems/root", "/filesystems/root")

    def test_remove_source_inherited_initial(self):
        self.remove_item("/storage")

        node1_storage = self.manager.get_item("/nodes/node1/storage")
        self.assertIsNone(node1_storage)
        node2_storage = self.manager.get_item("/nodes/node2/storage")
        self.assertIsNone(node2_storage)
        fs = self.manager.get_item("/filesystems/root")
        self.assertIsNone(fs)

    def test_remove_source_inherited_mfr(self):
        self.manager.set_all_applied()

        self.remove_item("/filesystems/root")
        fs = self.manager.get_item("/filesystems/root")
        self.assertIsNotNone(fs)
        self.assertTrue(fs.is_for_removal())

        self.remove_item("/nodes/node2/storage")
        node2_storage = self.manager.get_item("/nodes/node2/storage")
        self.assertIsNotNone(node2_storage)
        self.assertTrue(node2_storage.is_for_removal())

        self.remove_item("/nodes/node1/storage")
        node1_storage = self.manager.get_item("/nodes/node1/storage")
        self.assertIsNotNone(node1_storage)
        self.assertTrue(node1_storage.is_for_removal())

        self.remove_item("/storage")
        storage = self.manager.get_item("/storage")
        self.assertIsNotNone(storage)
        self.assertTrue(storage.is_for_removal())

    def test_1(self):
        self.manager.set_all_applied()

        # LITPCDS-12018: Allow removal of source with inherited items
        source = self.manager.remove_item("/nodes/node2/storage")

        inherited_fs = self.manager.get_item("/filesystems/root")
        self.assertIsNotNone(inherited_fs)
        self.assertTrue(inherited_fs.is_for_removal())

        self.remove_item("/nodes/node2/storage")
        node2_storage = self.manager.get_item("/nodes/node2/storage")
        self.assertIsNotNone(node2_storage)
        self.assertTrue(node2_storage.is_for_removal())

    def test_2(self):
        self.manager.set_all_applied()

        # LITPCDS-12018: Allow removal of source with inherited items
        inherited_source = self.manager.remove_item("/nodes/node1/storage")
        self.assertEqual(inherited_source.get_state(), ModelItem.ForRemoval)

        inherited_fs = self.manager.get_item("/filesystems/root")
        self.assertIsNotNone(inherited_fs)
        self.assertTrue(inherited_fs.is_for_removal())

        self.remove_item("/nodes/node2/storage")
        node2_storage = self.manager.get_item("/nodes/node2/storage")
        self.assertIsNotNone(node2_storage)
        self.assertTrue(node2_storage.is_for_removal())

        self.remove_item("/nodes/node1/storage")
        node1_storage = self.manager.get_item("/nodes/node1/storage")
        self.assertIsNotNone(node1_storage)
        self.assertTrue(node1_storage.is_for_removal())

    def test_3(self):
        self.manager.set_all_applied()

        storage_source = self.manager.remove_item("/storage")
        # LITPCDS-12018: Allow removal of source with inherited items
        self.assertEqual(storage_source.get_state(), ModelItem.ForRemoval)

        inherited_fs = self.manager.get_item("/filesystems/root")
        self.assertIsNotNone(inherited_fs)
        self.assertTrue(inherited_fs.is_for_removal())

        self.remove_item("/nodes/node2/storage")
        node2_storage = self.manager.get_item("/nodes/node2/storage")
        self.assertIsNotNone(node2_storage)
        self.assertTrue(node2_storage.is_for_removal())

        self.remove_item("/nodes/node1/storage")
        node1_storage = self.manager.get_item("/nodes/node1/storage")
        self.assertIsNotNone(node1_storage)
        self.assertTrue(node1_storage.is_for_removal())

        self.remove_item("/storage")
        storage = self.manager.get_item("/storage")
        self.assertIsNotNone(storage)
        self.assertTrue(storage.is_for_removal())

    def test_remove_source_initial_inherited_mfr(self):
        storage_inherited = self.manager.get_item("/nodes/node1/storage")
        storage_inherited.set_for_removal()

        self.manager.remove_item("/storage")
        storage = self.manager.get_item("/storage")
        self.assertIsNotNone(storage)
        self.assertTrue(storage.is_for_removal())

    def test_remove_source_inherited_applied_source_and_ref_for_removal(self):
        storage_inherited = self.manager.get_item("/nodes/node1/storage")
        storage_inherited.set_applied()

        source = self.manager.remove_item("/storage")
        # LITPCDS-12018: Allow removal of source with inherited items
        self.assertEqual(source.get_state(), ModelItem.ForRemoval)
        self.assertEqual(storage_inherited.get_state(), ModelItem.ForRemoval)

    def test_remove_source_inherited_2nd_level_applied_fails(self):
        root_inherited = self.manager.get_item("/filesystems/root")
        root_inherited.set_applied()

        source = self.manager.remove_item("/storage")
        # LITPCDS-12018: Allow removal of source with inherited items
        self.assertEqual(source.get_state(), ModelItem.ForRemoval)
        self.assertEqual(root_inherited.get_state(), ModelItem.ForRemoval)

    def test_remove_cascaded_inherited(self):
        self.create_inherited("/storage", "/nodes/node1/storages/s1")
        self.create_inherited("/nodes/node1/storages/s1", "/nodes/node1/storages/s2")

        self.remove_item("/storage")
        s1 = self.manager.get_item("/nodes/node1/storages/s1")
        self.assertIsNone(s1)
        s2 = self.manager.get_item("/nodes/node1/storages/s2")
        self.assertIsNone(s2)

class TestReadOnlyReferences(unittest.TestCase):
    def setUp(self):
        self.manager = ModelManager()
        self.manager.register_property_types([
            PropertyType("basic_string")
        ])
        self.manager.register_item_types([
            ItemType(
                "root",
                item=Child("foo"),
                ro=Child("ro"),
                rw=Child("rw")
            ),
            ItemType(
                "ro",
                ref=Reference("foo", read_only=True),
                refcoll=RefCollection("foo", read_only=True)
            ),
            ItemType(
                "rw",
                ref=Reference("foo"),
                refcoll=RefCollection("foo")
            ),
            ItemType(
                "foo",
                name=Property("basic_string"),
                subitem=Child("foo")
            )
        ])
        self.manager.create_root_item("root")
        self.manager.create_item("ro", "/ro")
        self.manager.create_item("rw", "/rw")
        self.manager.create_item("foo", "/item", name="name")
        self.manager.create_item("foo", "/item/subitem", name="name")

    def _assertErrorOccurred(self, exp_err_type, exp_err_message, result):
        error = result[0]
        self.assertTrue(isinstance(error, exp_err_type))
        self.assertEqual(error.error_message, exp_err_message)

    def test_inherit_with_properties(self):
        ret = self.manager.create_inherited("/item", "/ro/ref", name="x")
        self.assertFalse(isinstance(ret, ModelItem))
        self._assertErrorOccurred(ValidationError,
                'Read-only reference cannot be created with properties', ret)

    def test_inherit_with_properties_under_refcollection(self):
        ret = self.manager.create_inherited("/item", "/ro/refcoll/item", name="x")
        self.assertFalse(isinstance(ret, ModelItem))
        self._assertErrorOccurred(ValidationError,
                'Read-only reference cannot be created with properties', ret)

    def test_update(self):
        ret = self.manager.create_inherited("/item", "/ro/ref")
        self.assertTrue(isinstance(ret, ModelItem))
        ret = self.manager.update_item("/ro/ref", name="x")
        self.assertFalse(isinstance(ret, ModelItem))
        self._assertErrorOccurred(ValidationError,
                'Read-only reference cannot be updated', ret)
        ret = self.manager.update_item("/ro/ref/subitem", name="x")
        self.assertFalse(isinstance(ret, ModelItem))
        self._assertErrorOccurred(ValidationError,
                'Read-only reference cannot be updated', ret)

    def test_update_under_refcollection(self):
        ret = self.manager.create_inherited("/item", "/ro/refcoll/item")
        self.assertTrue(isinstance(ret, ModelItem))
        ret = self.manager.update_item("/ro/refcoll/item", name="x")
        self.assertFalse(isinstance(ret, ModelItem))
        self._assertErrorOccurred(ValidationError,
                'Read-only reference cannot be updated', ret)
        ret = self.manager.update_item("/ro/refcoll/item/subitem", name="x")
        self.assertFalse(isinstance(ret, ModelItem))
        self._assertErrorOccurred(ValidationError,
                'Read-only reference cannot be updated', ret)

    def test_inherit_inherited_readonly(self):
        ret = self.manager.create_inherited("/item", "/ro/ref")
        self.assertTrue(isinstance(ret, ModelItem))
        ret = self.manager.create_inherited("/ro/ref", "/rw/ref", name="x")
        self.assertTrue(isinstance(ret, ModelItem))

    def test_inherit_inherited_under_refcollection_readonly(self):
        ret = self.manager.create_inherited("/item", "/ro/refcoll/item")
        self.assertTrue(isinstance(ret, ModelItem))
        ret = self.manager.create_inherited("/ro/refcoll/item", "/rw/refcoll/item", name="x")
        self.assertTrue(isinstance(ret, ModelItem))

    def test_update_inherited_readonly(self):
        ret = self.manager.create_inherited("/item", "/ro/ref")
        self.assertTrue(isinstance(ret, ModelItem))
        ret = self.manager.create_inherited("/ro/ref", "/rw/ref")
        self.assertTrue(isinstance(ret, ModelItem))
        ret = self.manager.update_item("/rw/ref", name="x")
        self.assertTrue(isinstance(ret, ModelItem))
        ret = self.manager.update_item("/rw/ref/subitem", name="x")
        self.assertTrue(isinstance(ret, ModelItem))

    def test_update_inherited_under_refcollection_readonly(self):
        ret = self.manager.create_inherited("/item", "/ro/refcoll/item")
        self.assertTrue(isinstance(ret, ModelItem))
        ret = self.manager.create_inherited("/ro/refcoll/item", "/rw/refcoll/item")
        self.assertTrue(isinstance(ret, ModelItem))
        ret = self.manager.update_item("/rw/refcoll/item", name="x")
        self.assertTrue(isinstance(ret, ModelItem))
        ret = self.manager.update_item("/rw/refcoll/item/subitem", name="x")
        self.assertTrue(isinstance(ret, ModelItem))

    def test_inherit_inherited_child_readonly(self):
        ret = self.manager.create_inherited("/item", "/ro/ref")
        self.assertTrue(isinstance(ret, ModelItem))
        ret = self.manager.create_inherited("/ro/ref/subitem", "/rw/ref", name="x")
        self.assertTrue(isinstance(ret, ModelItem))

    def test_inherit_inherited_child_under_refcollection_readonly(self):
        ret = self.manager.create_inherited("/item", "/ro/refcoll/item")
        self.assertTrue(isinstance(ret, ModelItem))
        ret = self.manager.create_inherited("/ro/refcoll/item/subitem", "/rw/refcoll/item", name="x")
        self.assertTrue(isinstance(ret, ModelItem))

    def test_update_inherited_child_readonly(self):
        ret = self.manager.create_inherited("/item", "/ro/ref")
        self.assertTrue(isinstance(ret, ModelItem))
        ret = self.manager.create_inherited("/ro/ref/subitem", "/rw/ref")
        self.assertTrue(isinstance(ret, ModelItem))
        ret = self.manager.update_item("/rw/ref", name="x")
        self.assertTrue(isinstance(ret, ModelItem))

    def test_update_inherited_child_under_refcollection_readonly(self):
        ret = self.manager.create_inherited("/item", "/ro/refcoll/item")
        self.assertTrue(isinstance(ret, ModelItem))
        ret = self.manager.create_inherited("/ro/refcoll/item/subitem", "/rw/refcoll/item")
        self.assertTrue(isinstance(ret, ModelItem))
        ret = self.manager.update_item("/rw/refcoll/item", name="x")
        self.assertTrue(isinstance(ret, ModelItem))
