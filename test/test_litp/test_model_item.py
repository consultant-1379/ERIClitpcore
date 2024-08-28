
import unittest

from litp.core.model_type import Property
from litp.core.model_type import PropertyType
from litp.core.model_type import Child
from litp.core.model_type import Reference, RefCollection
from litp.core.model_type import Collection
from litp.core.model_type import View
from litp.core.model_type import ItemType
from litp.core.model_item import ModelItem
from litp.core.model_manager import ModelManager, ModelManagerException


class MockModelManager(ModelManager):
    def __init__(self):
        super(MockModelManager, self).__init__()

    def register_item_type(self, item_type):
        self.item_types[item_type.item_type_id] = item_type
        self._update_structure_property(item_type)


class ItemTest(unittest.TestCase):
    def _create_model_item(self, *args, **kwargs):
        return self.manager._create_model_item(*args, **kwargs)[0]

    @staticmethod
    def view_method(*args, **kwargs):
        return "test_view_value2"

    def setUp(self):
        self.root_item = ItemType("root",
                test_item=Child("test_item"),
                package=Child("package"),
                ms=Child("ms", require="node"),
                nodes=Collection("node"),
                vcs_cluster=Child("vcs-cluster")
        )
        self.inner_type = ItemType("inner_item",
            name=Property("basic_string"),
        )
        self.item_type = ItemType("test_item",
            name=Property("basic_string"),
            subobject=Child("inner_item"),
            package=Reference("package", name="wget", version="1.1"),
        )
        self.package_type = ItemType("package",
            name=Property("basic_string"),
            extensions=Collection("package_extension"),
            view_testview1=View("basic_string", 'test_view_value1'),
            view_testview2=View("basic_string", self.view_method)
        )
        self.package_extension_type = ItemType("package_extension",
            name=Property("basic_string"),
        )

        self.node_type = ItemType("node",
                hostname=Property("basic_string"),
                package=Reference("package"),
                custom_name=Property("basic_string"),
        )
        self.ms_type = ItemType("ms",
                hostname=Property("basic_string"),
        )
        self.clustered_service_type = ItemType("clustered-service",
            item_prop=Property("basic_string")
        )
        self.vcs_cluster_type = ItemType(
            "vcs-cluster",
            vcs_clustered_service=Child("vcs-clustered-service")
        )
        self.vcs_clustered_service_type = ItemType(
            "vcs-clustered-service",
            extend_item="clustered-service",
            item_prop=Property("basic_string")
        )

        self.basic_string = PropertyType("basic_string")
        self.integer = PropertyType("integer")

        self.manager = MockModelManager()
        self.manager.register_property_type(self.basic_string)
        self.manager.register_property_type(self.integer)
        self.manager.register_item_type(self.root_item)
        self.manager.register_item_type(self.node_type)
        self.manager.register_item_type(self.ms_type)
        self.manager.register_item_type(self.inner_type)
        self.manager.register_item_type(self.item_type)
        self.manager.register_item_type(self.package_type)
        self.manager.register_item_type(self.package_extension_type)
        self.manager.register_item_type(self.vcs_cluster_type)
        self.manager.register_item_type(self.clustered_service_type)
        self.manager.register_item_type(self.vcs_clustered_service_type)


    def _create_deployment_and_a_couple_of_nodes(self):
        root = self.manager.create_root_item("root")
        node1 = self.manager.create_item("node", "/nodes/node1",
            hostname="node1", custom_name="original_name")
        node2 = self.manager.create_item("node", "/nodes/node2",
            hostname="node2", custom_name="original_name")
        return root, node1, node2

    def test_creation(self):
        item = self._create_model_item(
            None, "test_item", "item1", dict(name="hello"))
        self.assertEqual("hello", item.name)

    def test_default_property(self):
        item_type = ItemType("itemtype",
                              no_default_1=Property("basic_string"),
                              no_default_2=Property("basic_string"),
                              default_1=Property("basic_string", default="1"),
                              default_2=Property("basic_string", default="abc"))
        self.manager.register_item_type(item_type)
        item = self._create_model_item(
            None, "itemtype", "item1", {})
        self.assertEqual(None, item.no_default_1)
        self.assertEqual(None, item.no_default_2)
        self.assertEqual(item.default_1, "1")
        self.assertEqual(item.default_2, "abc")

        # assertRises takes callable as an argument, so it can't be used here.
        try:
            item.non_existant
            self.fail("Should have thrown")
        except AssertionError:
            raise
        except AttributeError:
            pass

    def test_default_property_integer_values(self):
        item_type = ItemType("itemtype",
                             no_default_1=Property("integer"),
                             no_default_2=Property("integer"),
                             default_1=Property("integer", default="0"),
                             default_2=Property("integer", default="2"))
        self.manager.register_item_type(item_type)
        item = self._create_model_item(
            None, "itemtype", "item1", {})
        self.assertEqual(None, item.no_default_1)
        self.assertEqual(None, item.no_default_2)
        self.assertEqual(item.default_1, "0")
        self.assertEqual(item.default_2, "2")

        # assertRises takes callable as an argument, so it can't be used here.
        try:
            item.non_existant
            self.fail("Should have thrown")
        except AssertionError:
            raise
        except AttributeError:
            pass

    def test_item_type_validates_properties(self):
        self.assertRaises(TypeError,
                          ItemType,
                          "itemtype",
                          no_default_1=Property("integer"),
                          no_default_2=Property("integer"),
                          default_1="something")

    def test_regex_validator(self):
        prop_type = PropertyType("number_test_type", regex='^[0-9]+$')
        self.manager.register_property_type(prop_type)
        item_type = ItemType("item",
                             name=Property("number_test_type", required=True),
                             )
        self.manager.register_item_type(item_type)
        item1 = self._create_model_item(
            None, "item", "item1", {})
        item1._properties['name'] = "abc"
        self.assertEqual("abc", item1.name)

    def test_show(self):
        item_type = ItemType("basic",
            name=Property("basic_string", required=True),
            child_item=Child("child", required=True),
        )
        model_item = ModelItem(self.manager, item_type, "item", None, {'name': 'value1'})
        model_item.get_state = lambda: "Initial"

        self.assertEqual({'item_id': 'item', 'item_type': 'basic', 'status':
                           'Initial', 'properties': {'name': 'value1'}},
                          model_item.show_item())

    def test_set_property(self):
        item = self._create_model_item(
            None, "test_item", "item1", dict(name="hello"))

        item.set_applied()
        self.assertEquals(ModelItem.Applied, item.get_state())

        item.update_properties({"name": "foobar"})
        self.assertEquals(ModelItem.Updated, item.get_state())

        item.set_applied()
        self.assertEquals(ModelItem.Applied, item.get_state())

        item.set_property("name", "foobar")
        self.assertEquals(ModelItem.Applied, item.get_state())

    def test_previous_state_with_state_changes(self):
        # Test double calls to _set_state, to assert that state and
        # previous state do not get set to the same value.
        item = self._create_model_item(None, "test_item", "item1", {})
        self.assertEqual(item._state, ModelItem.Initial)
        self.assertEqual(item._previous_state, None)

        item.set_applied()
        self.assertEqual(item._previous_state, ModelItem.Initial)

        # Set applied again, previous state should still be Initial
        item.set_applied()
        self.assertEqual(item._previous_state, ModelItem.Initial)

        item.set_updated()
        self.assertEqual(item._previous_state, ModelItem.Applied)

        item.set_updated()
        self.assertEqual(item._previous_state, ModelItem.Applied)

        item.set_previous_state()
        self.assertEqual(item._previous_state, ModelItem.Updated)

        item.set_previous_state()
        self.assertEqual(item._previous_state, ModelItem.Applied)

        item.set_applied()
        item.set_for_removal()
        self.assertEqual(item._previous_state, ModelItem.Applied)
        item.set_for_removal()
        self.assertEqual(item._previous_state, ModelItem.Applied)
        item.set_removed()
        self.assertEqual(item._previous_state, ModelItem.Applied)
        item.set_removed()
        self.assertEqual(item._previous_state, ModelItem.Applied)

    def test_updated_status(self):
        item = self._create_model_item(
            None, "test_item", "item1", dict(name="hello"))

        item.set_applied()
        item.update_properties(dict(name="hello"))
        self.assertTrue(item.is_applied())

        item.update_properties(dict(name="different"))
        self.assertTrue(item.is_updated())

        item.update_properties(dict(name="hello"))
        self.assertTrue(item.is_applied())

    def test_updated_status_2(self):
        test_item = self._create_model_item(
            None, "test_item", "item1", dict(name="hello"))
        inner_item = test_item.subobject = self._create_model_item(
            None, "inner_item", "inner1", dict(name="blah"))

        inner_item.set_applied()
        test_item.set_applied()

        test_item.update_properties(dict(name="different"))
        inner_item.update_properties(dict(name="different"))

        self.assertTrue(test_item.is_updated())
        self.assertTrue(inner_item.is_updated())

    def test_children(self):
        root_item = self.manager.create_root_item("root")
        test_item = self.manager.create_item("test_item", "/test_item")
        package_item = self.manager.create_item("package", "/package")

        package_item.set_applied()

        package_item.update_properties(dict(name="SomeOtherValue"))

        self.assertTrue(package_item.is_updated())

        children = root_item.children
        self.assertTrue(package_item in children.values())
        self.assertTrue(test_item in children.values())

    def test_is_node(self):
        root_item = self.manager.create_root_item("root")
        test_item = self.manager.create_item("test_item", "/test_item")
        inner_item = self.manager.create_item("test_item", "/test_item")
        package_item = self.manager.create_item("package", "/package")
        package_extension_item = self.manager.create_item("package_extension",
                "/package/extensions/package_extension")
        node_item = self.manager.create_item("node", "/nodes/node")
        ms_item = self.manager.create_item("ms", "/ms")

        self.assertTrue(node_item.is_node())
        self.assertFalse(node_item.parent.is_node())
        self.assertTrue(ms_item.is_node())
        self.assertFalse(root_item.is_node())
        self.assertFalse(test_item.is_node())
        self.assertFalse(package_item.is_node())

    def test_get_node(self):
        root_item = self.manager.create_root_item("root")
        test_item = self.manager.create_item("test_item", "/test_item")
        inner_item = self.manager.create_item("test_item", "/test_item")
        package_item = self.manager.create_item("package", "/package")
        package_extension_item = self.manager.create_item("package_extension",
                "/package/extensions/package_extension")
        node_item = self.manager.create_item("node", "/nodes/node")
        ms_item = self.manager.create_item("ms", "/ms")

        self.assertTrue(self.manager.get_node(root_item) is None)
        self.assertTrue(self.manager.get_node(ms_item) is None)
        self.assertEquals(node_item.vpath, self.manager.get_node(node_item).vpath)
        self.assertTrue(self.manager.get_node(test_item) is None)
        self.assertTrue(self.manager.get_node(package_item) is None)

    def test_property_default(self):
        del self.manager
        self.manager = ModelManager()

        prop_type = PropertyType("basic_string")
        self.manager.register_property_type(prop_type)

        prop_not_req_no_default = Property(
                "basic_string",
                prop_description="foo",
                required=False,
                default=None)

        prop_not_req_has_default = Property(
                "basic_string",
                prop_description="foo",
                required=False,
                default="default_R0D1")

        prop_req_has_default = Property(
                "basic_string",
                prop_description="foo",
                required=True,
                default="default_R1D1")

        playground_type = ItemType("property_playground",
                R0D0=prop_not_req_no_default,
                R0D1=prop_not_req_has_default,
                R1D1=prop_req_has_default,
                )

        root_type = ItemType("root",
                foo=Child("property_playground", required=True)
                )

        self.manager.register_item_types((root_type, playground_type))
        root = self.manager.create_root_item("root")

        self.assertEquals([], self.manager.validator.validate_properties(playground_type, root.foo))

        self.assertEquals(None, root.foo.R0D0)
        self.assertEquals('default_R0D1', root.foo.R0D1)
        self.assertEquals('default_R1D1', root.foo.R1D1)

    def test_recreate_removed_previously_updated_item(self):
        # Recreate with applied properties
        root, node, node2 = self._create_deployment_and_a_couple_of_nodes()
        node.set_applied()
        node.update_properties({'custom_name': "updated_name"})
        self.assertEqual(ModelItem.Updated, node.get_state())
        self.manager.remove_item(node.vpath)
        self.assertEqual(ModelItem.ForRemoval, node.get_state())
        self.manager.create_item("node", "/nodes/node1",
                hostname="node1", custom_name="original_name")
        self.assertEqual(ModelItem.Applied, node.get_state())
        self.assertEqual("original_name", node.custom_name)
        # Recreate with updated properties
        node2.set_applied()
        node2.update_properties({'custom_name': "updated_name"})
        self.assertEqual(ModelItem.Updated, node2.get_state())
        self.manager.remove_item(node2.vpath)
        self.assertEqual(ModelItem.ForRemoval, node2.get_state())
        self.manager.create_item("node", "/nodes/node2",
                hostname="node2", custom_name="updated_name")
        self.assertEqual(ModelItem.Updated, node2.get_state())
        self.assertEqual("updated_name", node2.custom_name)

    def test_applied_properties_determinable(self):
        # 7855 AC 1. - New model item created, no plan run
        root, node, node2 = self._create_deployment_and_a_couple_of_nodes()
        self.assertEqual(ModelItem.Initial, node.get_state())
        self.assertEqual(True, node.applied_properties_determinable)
        # 7855 AC 3. - Model item updated but no plan is run
        node.set_applied()
        node.update_properties({'custom_name': "updated_name"})
        self.assertEqual(ModelItem.Updated, node.get_state())
        self.assertEqual(True, node.applied_properties_determinable)
        # 7855 AC 6. - Updated item, flag False, updated back to original
        node._set_applied_properties_determinable(False)
        node.update_properties({"custom_name": "original_name"})
        self.assertEqual(ModelItem.Updated, node.get_state())
        self.assertEqual("original_name", node.custom_name)
        # Check AC 6 doesn't affect existing behaviour
        node2.set_applied()
        node2.update_properties({"custom_name": "updated_name"})
        self.assertEqual(ModelItem.Updated, node2.get_state())
        self.assertEqual(True, node2.applied_properties_determinable)
        node2.update_properties({"custom_name": "original_name"})
        self.assertEqual(ModelItem.Applied, node2.get_state())
        self.assertEqual("original_name", node2.custom_name)
        # 7855 AC 2. - ModelItem set to applied state
        self.assertEqual(False, node.applied_properties_determinable)
        node.set_applied()
        self.assertEqual(True, node.applied_properties_determinable)

    def test_applied_properties_determinable_2(self):
        root, node, node2 = self._create_deployment_and_a_couple_of_nodes()
        # 7855 AC 7 - ForRemoval, flag is false, recreate item - was Initial
        node2._set_applied_properties_determinable(False)
        self.assertEqual(ModelItem.Initial, node2.get_state())
        self.manager.remove_item(node2.vpath)
        # 20150417
        #self.assertEqual(ModelItem.ForRemoval, node2.get_state())
        self.manager.create_item("node", "/nodes/node2",
            hostname="node2", custom_name="original_name")
        #self.assertEqual(ModelItem.Initial, node2.get_state())
        self.assertEqual("original_name", node2.custom_name)
        # 7855 AC 7 - ForRemoval, flag is false, recreate item - was Updated
        node.set_applied()
        node.update_properties({'custom_name': "updated_name"})
        node._set_applied_properties_determinable(False)
        self.assertEqual(ModelItem.Updated, node.get_state())
        self.manager.remove_item(node.vpath)
        self.assertEqual(ModelItem.ForRemoval, node.get_state())
        self.manager.create_item("node", "/nodes/node1",
            hostname="node1", custom_name="original_name")
        self.assertEqual(ModelItem.Updated, node.get_state())
        self.assertEqual("original_name", node.custom_name)
        # 7855 AC 7 - ForRemoval, flag is false, recreate item - was Applied
        node.set_applied()
        self.manager.remove_item(node.vpath)
        node._set_applied_properties_determinable(False)
        self.assertEqual(ModelItem.ForRemoval, node.get_state())
        self.manager.create_item("node", "/nodes/node1",
            hostname="node1", custom_name="original_name")
        self.assertEqual(ModelItem.Updated, node.get_state())
        self.assertEqual("original_name", node.custom_name)

    def test_applied_properties_determinable_3(self):
        root, node, node2 = self._create_deployment_and_a_couple_of_nodes()
        # 7855 AC 9 - Initial item, flag is true, item removed
        self.assertEqual(ModelItem.Initial, node.get_state())
        self.assertEqual(True, node.applied_properties_determinable)
        self.manager.remove_item(node.vpath)
        self.assertEqual(ModelItem.Removed, node.get_state())
        self.assertRaises(ModelManagerException, self.manager.query_by_vpath, node.vpath)
        # 7855 AC 10 - Initial item, flag is false, item removed
        node2._set_applied_properties_determinable(False)
        self.assertEqual(ModelItem.Initial, node2.get_state())
        self.assertEqual(False, node2.applied_properties_determinable)
        self.manager.remove_item(node2.vpath)
        # 20150417
        #self.assertEqual(ModelItem.ForRemoval, node2.get_state())

    def test_was_applied(self):
        root, node, node2 = self._create_deployment_and_a_couple_of_nodes()
        self.assertFalse(node.was_applied())
        node.set_applied()
        self.assertFalse(node.was_applied())
        self.manager.update_item(node.vpath, custom_name="updated_name")
        self.assertTrue(node.was_applied())
        self.manager.remove_item(node.vpath)
        self.assertFalse(node.was_applied())

    def test_was_initial(self):
        root, node, node2 = self._create_deployment_and_a_couple_of_nodes()
        self.assertFalse(node.was_initial())
        node.set_applied()
        self.assertTrue(node.was_initial())
        self.manager.update_item(node.vpath, custom_name="updated_name")
        self.assertFalse(node.was_initial())
        self.manager.remove_item(node.vpath)
        self.assertFalse(node.was_initial())

    def test_view(self):
        item = ModelItem(self.manager, self.package_type, "/package", "/")
        self.assertEquals("test_view_value1", item.view_testview1)
        self.assertEquals("test_view_value2", item.view_testview2())

    def test_was_removed(self):
        root, node, node2 = self._create_deployment_and_a_couple_of_nodes()
        self.assertFalse(node.was_removed())
        node.set_applied()
        self.assertFalse(node.was_removed())
        # Mimic plan removal failure
        self.manager.remove_item(node.vpath)
        self.assertFalse(node.was_removed())
        node.set_removed()
        self.assertFalse(node.was_removed())
        node.set_for_removal()
        self.assertTrue(node.was_removed())

    def test_item_equality_views(self):

        prop_type = PropertyType("prop_type")
        self.manager.register_property_type(prop_type)

        root_item_type = ItemType(
            "root",
            items=Collection("itemtype_with_view")
        )
        self.manager.register_item_type(root_item_type)

        def _view_callable(plugin_api_context, view_qi):
            return 'foo'

        view_item_type = ItemType(
            "itemtype_with_view",
            prop=Property("prop_type", default="def"),
            view=View(
                "prop_type",
                view_description="yay",
                callable_method=_view_callable
            )
        )
        self.manager.register_item_type(view_item_type)

        self.manager.create_root_item("root")
        item_a = ModelItem(self.manager, view_item_type, "arbitrary_id", None, {"prop":"hello"})
        item_b = ModelItem(self.manager, view_item_type, "arbitrary_id", None, {"prop":"hello"})

        self.assertTrue(item_a == item_b)
        self.assertTrue(item_b == item_a)

        def _other_view_callable(a, b):
            return "bar"

        item_b._properties['view'] = _other_view_callable
        self.assertFalse(item_a == item_b)
        self.assertFalse(item_b == item_a)

    def test_is_vcs_clustered_service(self):
        root_item = self.manager.create_root_item("root")
        package_item = self.manager.create_item("package", "/package")
        cluster_item = self.manager.create_item("vcs-cluster", "/vcs_cluster")
        vcs_item = self.manager.create_item("vcs-clustered-service",
                                         "/vcs_cluster/vcs_clustered_service")

        self.assertFalse(root_item.is_type("clustered-service"))
        self.assertFalse(package_item.is_type("clustered-service"))
        self.assertFalse(cluster_item.is_type("clustered-service"))
        self.assertFalse(vcs_item.parent.is_type("clustered-service"))
        self.assertTrue(vcs_item.is_type("clustered-service"))

    def test_get_vcs_clustered_service(self):
        root_item = self.manager.create_root_item("root")
        package_item = self.manager.create_item("package", "/package")
        package_extension_item = self.manager.create_item("package_extension",
                                      "/package/extensions/package_extension")
        cluster_item = self.manager.create_item("vcs-cluster", "/vcs_cluster")
        vcs_item = self.manager.create_item("vcs-clustered-service",
                                         "/vcs_cluster/vcs_clustered_service")

        self.assertTrue(self.manager.get_ancestor(
            root_item, "clustered-service") is None)
        self.assertTrue(self.manager.get_ancestor(
            package_item, "clustered-service") is None)
        self.assertTrue(self.manager.get_ancestor(
            package_extension_item, "clustered-service") is None)
        self.assertTrue(self.manager.get_ancestor(
            package_item, "clustered-service") is None)
        self.assertEquals(vcs_item.vpath,
           self.manager.get_ancestor(vcs_item, "clustered-service").vpath)


class ItemTest2(unittest.TestCase):
    # using ModelManager instead of the mocked one

    def setUp(self):
        self.manager = ModelManager()

    def _create_applied_root_parent_child_model(self):
        root_item_type = ItemType("root", parent=Child("parent"))
        parent_item_type = ItemType("parent",
                name=Property("basic_string"),
                child=Child("child"),
        )
        child_item_type = ItemType("child",
                name=Property("basic_string"),
        )
        self.manager.register_property_type(PropertyType("basic_string"))
        self.manager.register_item_types([root_item_type, parent_item_type, child_item_type])

        root = self.manager.create_root_item("root")
        parent = self.manager.create_item("parent", "/parent", name="caretaker")
        child = self.manager.create_item("child", "/parent/child", name="offspring")
        self.manager.set_all_applied()

        return root, parent, child

    def test_item_extends(self):
        self.manager.register_item_types([
            ItemType(
                "root",
                item=Child("foo")
            ),
            ItemType(
                "foo"
            ),
            ItemType(
                "foo2",
                extend_item="foo"
            ),
            ItemType(
                "foo3",
                extend_item="foo2"
            )
        ])

        self.manager.create_root_item("root")
        item = self.manager.create_item("foo3", "/item")

        self.assertTrue(item._extends("foo3"))
        self.assertTrue(item._extends("foo2"))
        self.assertTrue(item._extends("foo"))

    def test_set_state_child_collection(self):
        self.manager.register_property_types([
            PropertyType("basic_string", regex=r"^[a-zA-Z0-9\-\._]+$"),
            PropertyType("basic_list",
                         regex=r"^[a-zA-Z0-9\-\._]*(,[a-zA-Z0-9\-\._]+)*$"),
            ])
        self.manager.register_item_type(ItemType(
            "root",
            name=Property("basic_string"),
            item=Child("item"),
            source=Child("other-item"),
        ))
        self.manager.register_item_type(ItemType(
            "item",
            name=Property("basic_string"),
            ref=Reference("other-item"),
            items=Collection("item")
        ))
        self.manager.register_item_type(ItemType(
        "other-item",
        ref=Reference("item"),
        ))

        self.manager.create_root_item("root")
        source = self.manager.create_item("other-item", "/source")
        self.manager.create_item("item", "/item",name="original_name" )

        parent = self.manager.get_item("/item")
        child = self.manager.create_item("item", "/item/items/item1")
        item = self.manager.get_item("/item/items")

        parent2 = self.manager.create_inherited("/item",
            "/source/ref")
        child2 = self.manager.get_item("/source/ref/items/item1")
        item2 = self.manager.get_item("/source/ref/items")

        self.manager.set_all_applied()
        self.manager.remove_item(parent2.vpath)
        self.manager.update_item(parent.vpath, name='original_name')

        self.assertEqual(child2.get_state(), ModelItem.ForRemoval)
        self.assertEqual(item2.get_state(), ModelItem.Applied)
        self.assertEqual(parent2.get_state(), ModelItem.Applied)

    def test_applied_properties_determinable_false_forremoval_children(self):
        # Create parent item that has a child item
        root, parent, child = self._create_applied_root_parent_child_model()
        # Set applied items for removal (was applied)
        self.manager.remove_item(child.vpath)
        self.manager.remove_item(parent.vpath)
        self.assertEqual(ModelItem.ForRemoval, child.get_state())
        self.assertEqual(ModelItem.ForRemoval, parent.get_state())
        # Set APD of child to false and leave parent APD as true
        child._set_applied_properties_determinable(False)
        self.assertEqual(False, child.applied_properties_determinable)
        self.assertEqual(True, parent.applied_properties_determinable)
        # Recreate parent with applied propetes
        parent = self.manager.create_item("parent", "/parent", name="caretaker")
        self.assertEqual(ModelItem.Applied, parent.get_state())
        # Child should not go back to Applied as APD is False, goes to Updated
        self.assertEqual(ModelItem.Updated, child.get_state())
        self.assertEqual(False, child.applied_properties_determinable)
        # Updated the child item -> stays in Updated and APD False
        child.update_properties({"name": "updated_offspring"})
        self.assertEqual(ModelItem.Updated, child.get_state())
        self.assertEqual(False, child.applied_properties_determinable)

    def test_applied_properties_determinable_true_forremoval_children(self):
        # Create parent item that has a child item
        root, parent, child = self._create_applied_root_parent_child_model()
        # Set applied items for removal (was applied)
        self.manager.remove_item(child.vpath)
        self.manager.remove_item(parent.vpath)
        self.assertEqual(ModelItem.ForRemoval, child.get_state())
        self.assertEqual(ModelItem.ForRemoval, parent.get_state())
        self.assertEqual(True, child.applied_properties_determinable)
        self.assertEqual(True, parent.applied_properties_determinable)
        # Recreate parent with applied propetes
        parent = self.manager.create_item("parent", "/parent", name="caretaker")
        self.assertEqual(ModelItem.Applied, parent.get_state())
        # Child should go back to Applied as APD is True
        self.assertEqual(ModelItem.Applied, child.get_state())
        self.assertEqual(True, child.applied_properties_determinable)
        # Updated the child item -> goes to Updated and APD stays True
        child.update_properties({"name": "updated_offspring"})
        self.assertEqual(ModelItem.Updated, child.get_state())
        self.assertEqual(True, child.applied_properties_determinable)

    def test_no_such_attribute(self):
        prop_type = PropertyType("prop_type")
        self.manager.register_property_type(prop_type)

        root_item_type = ItemType("root", item=Child("itemtype"))
        self.manager.register_item_type(root_item_type)

        item_type = ItemType(
            "itemtype",
            prop=Property("prop_type", default="def")
        )
        self.manager.register_item_type(item_type)


        self.manager.create_root_item("root")
        item = self.manager.create_item("itemtype", "/item")

        self.assertFalse(hasattr(item, 'does_not_exist'))
        self.assertRaises(AttributeError, getattr, item, 'does_not_exist')

    def test_update_source_apd_false_reference(self):
        # Update source from CLI to go back to applied state, reference has
        # APD=False so it should stay in Updated state (not Applied)
        model = ModelManager()
        model.register_property_types([
            PropertyType("basic_string", regex=r"^[a-zA-Z0-9\-\._]+$"),
        ])
        model.register_item_type(ItemType(
            "root",
            container=Child("container"),
            container_two=Child("container-two"),
            source=Child("item"),
        ))
        model.register_item_type(ItemType(
            "container",
            ref1=Reference("item")
        ))
        model.register_item_type(ItemType(
            "container-two",
            ref2=Reference("item")
        ))
        model.register_item_type(ItemType(
            "item",
            name=Property("basic_string")
        ))
        model.create_root_item("root")
        model.create_item("container", "/container")
        model.create_item("container-two", "/container_two")
        source = model.create_item("item", "/source", name='original_name')
        ref1 = model.create_inherited("/source", "/container/ref1")
        ref2 = model.create_inherited("/source", "/container_two/ref2")
        model.set_all_applied()
        model.update_item(source.vpath, name='new_name_for_all')
        ref1._set_applied_properties_determinable(False)
        model.update_item(source.vpath, name='original_name')
        self.assertEqual(ModelItem.Updated, ref1.get_state())
        self.assertEqual(ModelItem.Applied, ref2.get_state())


    def test_overwritten_properties(self):
        model = ModelManager()
        model.register_property_types([
            PropertyType("basic_string", regex=r"^[a-zA-Z0-9\-\._]+$"),
        ])
        model.register_item_type(ItemType(
            "root",
            container=Child("container"),
            source=Child("item"),
        ))
        model.register_item_type(ItemType(
            "container",
            refs=RefCollection("item")
        ))
        model.register_item_type(ItemType(
            "item",
            prop1=Property("basic_string"),
            prop2=Property("basic_string"),
            prop3=Property("basic_string")
        ))
        model.create_root_item("root")
        model.create_item("container", "/container")
        source = model.create_item("item", "/source", prop1='original_prop1')
        ref = model.create_inherited("/source", "/container/refs/ref")
        # At creation, ref props not overwritten
        self.assertFalse(source.has_overwritten_properties)
        self.assertFalse(ref.has_overwritten_properties)
        self.assertFalse(source.is_property_overwritten('prop1'))
        self.assertFalse(ref.is_property_overwritten('prop1'))
        self.assertFalse(ref.is_property_overwritten('NOTTHERE'))
        self.assertFalse(source.all_properties_overwritten({'prop1':1, 'prop2':2, 'prop3':3}))
        self.assertFalse(ref.all_properties_overwritten({'prop1':1, 'prop2':2, 'prop3':3}))
        self.assertFalse(ref.all_properties_overwritten({'NOPROP':'1'}))
        self.assertFalse(ref.all_properties_overwritten({}))
        # Update source, ref props not overwritten
        source.set_property('prop1', 'original_prop1_two')
        self.assertFalse(source.has_overwritten_properties)
        self.assertFalse(ref.has_overwritten_properties)
        self.assertFalse(source.is_property_overwritten('prop1'))
        self.assertFalse(ref.is_property_overwritten('prop1'))
        self.assertFalse(source.all_properties_overwritten({'prop1':1, 'prop2':2, 'prop3':3}))
        self.assertFalse(ref.all_properties_overwritten({'prop1':1, 'prop2':2, 'prop3':3}))
        # Update source with new prop, ref props not overwritten
        source.set_property('prop2', 'original_prop1_two')
        self.assertFalse(source.has_overwritten_properties)
        self.assertFalse(ref.has_overwritten_properties)
        self.assertFalse(source.is_property_overwritten('prop2'))
        self.assertFalse(ref.is_property_overwritten('prop2'))
        self.assertFalse(source.all_properties_overwritten({'prop1':1, 'prop2':2, 'prop3':3}))
        self.assertFalse(ref.all_properties_overwritten({'prop1':1, 'prop2':2, 'prop3':3}))
        # Update new ref props, ref props overwritten
        ref.set_property('prop3', 'ref_overwrites_prop3')
        self.assertFalse(source.has_overwritten_properties)
        self.assertTrue(ref.has_overwritten_properties)
        self.assertFalse(source.is_property_overwritten('prop3'))
        self.assertTrue(ref.is_property_overwritten('prop3'))
        self.assertFalse(source.all_properties_overwritten({'prop1':1, 'prop2':2, 'prop3':3}))
        self.assertFalse(ref.all_properties_overwritten({'prop1':1, 'prop2':2, 'prop3':3}))
        self.assertTrue(ref.all_properties_overwritten({'prop3':3}))
        # Remove the updated ref prop, ref props not overwritten
        ref.set_property('prop3', None)
        self.assertFalse(source.has_overwritten_properties)
        self.assertFalse(ref.has_overwritten_properties)
        self.assertFalse(source.is_property_overwritten('prop3'))
        self.assertFalse(ref.is_property_overwritten('prop3'))
        self.assertFalse(source.all_properties_overwritten({'prop1':1, 'prop2':2, 'prop3':3}))
        self.assertFalse(ref.all_properties_overwritten({'prop1':1, 'prop2':2, 'prop3':3}))
        self.assertFalse(ref.all_properties_overwritten({'prop3':3}))
        # Update existing ref props, ref props overwritten
        ref.set_property('prop1', 'ref_overwrites_prop1')
        self.assertFalse(source.has_overwritten_properties)
        self.assertTrue(ref.has_overwritten_properties)
        self.assertFalse(source.is_property_overwritten('prop1'))
        self.assertTrue(ref.is_property_overwritten('prop1'))
        self.assertFalse(source.all_properties_overwritten({'prop1':1, 'prop2':2, 'prop3':3}))
        self.assertFalse(ref.all_properties_overwritten({'prop1':1, 'prop2':2, 'prop3':3}))
        self.assertTrue(ref.all_properties_overwritten({'prop1':1}))
        # Applied state
        ref2 = model.create_inherited("/source", "/container/refs/ref2")
        ref.set_applied()
        ref2.set_applied()
        source.set_applied()
        self.assertFalse(source.has_overwritten_properties)
        self.assertTrue(ref.has_overwritten_properties)
        # Applied ref with no overwrites
        self.assertFalse(source.has_overwritten_properties)
        self.assertFalse(ref2.has_overwritten_properties)
        self.assertFalse(source.is_property_overwritten('prop1'))
        self.assertFalse(ref2.is_property_overwritten('prop1'))
        self.assertFalse(source.all_properties_overwritten({'prop1':1, 'prop2':2, 'prop3':3}))
        self.assertFalse(ref2.all_properties_overwritten({'prop1':1, 'prop2':2, 'prop3':3}))
        # Update applied source, ref props not overwritten
        source.set_property('prop1', 'updated_source_prop1')
        self.assertFalse(source.has_overwritten_properties)
        self.assertFalse(ref2.has_overwritten_properties)
        self.assertFalse(source.is_property_overwritten('prop1'))
        self.assertFalse(ref2.is_property_overwritten('prop1'))
        self.assertFalse(source.all_properties_overwritten({'prop1':1, 'prop2':2, 'prop3':3}))
        self.assertFalse(ref2.all_properties_overwritten({'prop1':1, 'prop2':2, 'prop3':3}))
        # Update ref with same value as source, ref overwritten
        ref2.set_property('prop1', source.prop1)
        self.assertFalse(source.has_overwritten_properties)
        self.assertTrue(ref2.has_overwritten_properties)
        self.assertTrue(ref2.is_property_overwritten('prop1'))
        self.assertFalse(ref2.is_property_overwritten('prop2'))
        self.assertFalse(source.all_properties_overwritten({'prop1':1, 'prop2':2, 'prop3':3}))
        self.assertTrue(ref2.all_properties_overwritten({'prop1':1}))
        # Update ref again with now prop, ref overwritten
        ref2.set_property('prop3', 'ref_overwrites_prop3')
        self.assertFalse(source.has_overwritten_properties)
        self.assertTrue(ref2.has_overwritten_properties)
        self.assertTrue(ref2.is_property_overwritten('prop3'))
        self.assertFalse(ref2.is_property_overwritten('prop2'))
        self.assertFalse(ref2.all_properties_overwritten({'prop2':2}))
        self.assertTrue(ref2.all_properties_overwritten({'prop1':1, 'prop3':3}))
        # Overwrite all ref properties
        ref2.set_property('prop2', 'ref_overwrites_prop2')
        self.assertTrue(ref2.all_properties_overwritten({'prop1':1, 'prop2':2, 'prop3':3}))
