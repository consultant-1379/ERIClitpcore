 # -*- coding: utf-8 -*-
import unittest
import logging
import StringIO
import mock

from litp.core.model_manager import ModelManager
from litp.core.model_manager import ModelManagerException
from litp.core.model_manager import QueryItem
from litp.core.model_item import ModelItem
from litp.core.model_type import ItemType
from litp.core.model_type import Child
from litp.core.model_type import Collection
from litp.core.model_item import CollectionItem
from litp.core.model_type import Property
from litp.core.model_type import View
from litp.core.model_type import Reference
from litp.core.model_type import RefCollection
from litp.core.model_type import PropertyType
from litp.core.validators import ValidationError, \
    NetworkValidator, IsNotDigitValidator, \
    ZeroAddressValidator, NotEmptyStringValidator
from litp.extensions.core_extension import MSValidator
from litp.extensions.core_extension import CoreExtension
from litp.core.future_property_value import FuturePropertyValue
from litp.core.task import Task, ConfigTask
from litp.core.plugin_context_api import PluginApiContext

from litp.core import constants
from litp.core.exceptions import CyclicGraphException, ViewError


class MockTask(object):
    def __init__(self):
        self.state = ModelItem.Initial
        self.type = Task.TYPE_OTHER
        self.is_snapshot_task = False


class ModelManagerTest(unittest.TestCase):
    def setUp(self):
        self.manager = ModelManager()
        self.api = PluginApiContext(self.manager)
        self.manager.register_property_type(PropertyType("basic_regex_string", regex=r"^[a-zA-Z0-9\-\._]+$"))
        self.manager.register_property_type(PropertyType("basic_string"))
        self.manager.register_property_type(PropertyType("basic_boolean", regex=r"^(true|false)$"))
        self.manager.register_property_type(PropertyType("special_string",
                                                         regex="^[a-z]+$"))
        self.manager.register_property_type(PropertyType("network", regex=r"^[0-9\./]+$",
                validators=[NotEmptyStringValidator(), NetworkValidator(),
                ZeroAddressValidator()]))
        self.manager.register_property_type(PropertyType("hostname",
                         regex=r"^(\.[a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9\-]"\
                         "{0,61}[a-zA-Z0-9])$",
                         validators=[IsNotDigitValidator()]))
        self.manager.register_property_type(PropertyType("custom_boolean",
                regex=r"^(true|false)$",
                regex_error_desc="Some error description."))

        self.manager.register_property_type(
            PropertyType(
                "basic_list",
                regex=r"^[a-zA-Z0-9\-\._]*(,[a-zA-Z0-9\-\._]+)*$")
        )
        self.mock_node_type = ItemType(
            "mock-node",
            hostname=Property("basic_string"),
            extend_item="node"
        )

    def _setUp_model_for_property_validation_tests(self):
        self.manager.register_item_type(ItemType(
            "root",
            infrastructure=Child("infrastructure"),
            ms=Child("ms", required=False),
        ))
        self.manager.register_item_type(ItemType(
                "infrastructure",
                networking=Child("networking", required=True),
        ))
        self.manager.register_item_type(ItemType(
                "networking",
                networks=Collection("network"),
        ))
        self.manager.register_item_type(ItemType(
                "network",
                name=Property("basic_regex_string",
                    required=True),
                subnet=Property("network",
                    required=False),
                dummy_bool=Property("custom_boolean")
        ))
        self.manager.register_item_type(ItemType(
                "ms",
                validators=[MSValidator()],
                hostname=Property(
                    "hostname",
                    required=True,
                ),
        ))
        self.manager.create_root_item("root")

    def _create_simple_parent_child_structure(self):
        self.manager.register_item_type(ItemType(
            "root",
            item=Child("item"),
        ))
        self.manager.register_item_type(ItemType(
            "item",
            items=Collection("item")
        ))
        self.manager.create_root_item("root")
        self.manager.create_item("item", "/item")
        self.manager.create_item("item", "/item/items/item1")
        self.manager.create_item("item", "/item/items/item1/items/item2")

    def _create_sibbling_structure(self):
        self.manager.register_item_type(ItemType(
            "root",
            item=Child("item"),
            some_item=Child("some-item")
        ))
        self.manager.register_item_type(ItemType(
            "item",
            some_item=Reference("some-item"),
            another_item=Child("another-item")
        ))
        self.manager.register_item_type(ItemType("some-item",
            name=Property("basic_string",
                    updatable_rest=False)
            ))
        self.manager.register_item_type(ItemType(
            "another-item",
            yet_another_item=Child("yet-another-item")
        ))
        self.manager.register_item_type(ItemType("yet-another-item"))

        self.manager.create_root_item("root")
        self.manager.create_item("item", "/item")
        self.manager.create_item("another-item", "/item/another_item")
        self.manager.create_item("yet-another-item", "/item/another_item/yet_another_item")
        self.manager.create_item("some-item", "/some_item")
        self.manager.create_inherited("/some_item",
            "/item/some_item")

    def test_show_new_model_item(self):
        self.manager.register_item_type(ItemType("root",
            my_child=Child("child"),
            my_dependant=Child("dependant"),
            name=Property("basic_string")
        ))
        self.manager.register_item_type(ItemType("child",
            dependant_ref=Reference("dependant"),
            name=Property("basic_string", required=True)
        ))
        self.manager.register_item_type(ItemType("dependant",
            name=Property("basic_string", required=True)
        ))

        root = self.manager.create_root_item("root")
        child = self.manager.create_item("child", "/my_child",
                                         name="test")
        self.assertEqual(self.manager.show("/my_child"),
                          self.manager.get_item("/my_child").show_item())

    def test_show_new_model_item_2(self):
        self.manager.register_item_type(ItemType("root",
            my_child=Child("child"),
            my_dependant=Child("dependant"),
            name=Property("basic_string")
        ))
        self.manager.register_item_type(ItemType("child",
            dependant_ref=Reference("dependant"),
            name=Property("basic_string", required=True)
        ))
        self.manager.register_item_type(ItemType("dependant",
            name=Property("basic_string", required=True)
        ))

        root = self.manager.create_root_item("root")
        child = self.manager.create_item("child", "/my_child",
                                         name="test")
        self.assertEqual(self.manager.show("/my_child"),
                          self.manager.get_item("/my_child").show_item())

    def test_not_allowed_overwrite(self):
        t1 = ItemType(
            "super",
            foo=Property("basic_string")
        )
        t2 = ItemType(
            "sub",
            extend_item="super",
            foo=Property("basic_string")
        )
        self.manager.register_item_type(t1)
        self.assertRaises(Exception, self.manager.register_item_type, t2)

    def test_not_allowed_child(self):
        self.manager.register_item_type(ItemType("root",
            my_child=Child("child")
        ))
        self.manager.register_item_type(ItemType("child",
            name=Property("basic_string", required=True)
        ))
        root = self.manager.create_root_item("root")
        # test invalid item type
        output = self.manager.create_item("nope", "/nonexistant")
        validation_error = output[0].to_dict()
        self.assertEqual(validation_error['uri'], '/nonexistant')
        self.assertEqual(validation_error['message'],
                         'Item type not registered: nope')
        self.assertEqual(validation_error['error'], 'InvalidTypeError')

        # test invalid item id
        output = self.manager.create_item("child", "/%&^", name="test")
        validation_error = output[0].to_dict()
        self.assertEqual(validation_error['property_name'], '%&^')
        self.assertEqual(validation_error['message'],
                         "Invalid value for item id: '%&^'")
        self.assertEqual(validation_error['error'], 'ValidationError')

        # create an empty item id
        output = self.manager.create_item("child", "/", name="test")
        validation_error = output[0].to_dict()
        self.assertEqual(validation_error['property_name'], 'item id')
        self.assertEqual(validation_error['message'],
                         "Invalid value for item id: ''")
        self.assertEqual(validation_error['error'], 'ValidationError')

    def test_items_with_references(self):
        self.manager.register_item_type(ItemType("root",
            my_child=Child("child"),
            my_dependant=Child("dependant"),
            name=Property("basic_string")
        ))
        self.manager.register_item_type(ItemType("child",
            dependant_ref=Reference("dependant"),
            name=Property("basic_string", required=True)
        ))
        self.manager.register_item_type(ItemType("dependant",
            name=Property("basic_string", required=True)
        ))

        root = self.manager.create_root_item("root")
        child = self.manager.create_item("child", "/my_child",
                                         name="child")
        dependant = self.manager.create_item("dependant", "/my_dependant",
            name="depend1")
        dependant_ref = self.manager.create_inherited(
            "/my_dependant",
            "/my_child/dependant_ref")

        self.assertEqual(child, self.manager.get_item("/my_child"))
        self.assertEqual(dependant, self.manager.get_item(
            "/my_dependant"))
        self.assertEqual(dependant_ref, self.manager.get_item(
            "/my_child/dependant_ref"))

        self.assertEqual(child, root.my_child)
        self.assertEqual(dependant, root.my_dependant)

        self.assertTrue(self.manager._match(dependant, 'dependant',
            dependant_ref._properties))
        self.assertEqual(dependant.vpath, root.my_child.dependant_ref.source_vpath)

        dependant_ref2 = self.manager.update_item(
                "/my_child/dependant_ref", name="depend2")
        self.assertEqual("depend2", dependant_ref2.name)

    def test_parent_child_relationship(self):
        self.manager.register_item_type(ItemType("root",
            my_child=Child("child"),
            my_dependant=Child("dependant"),
            name=Property("basic_string")
        ))
        self.manager.register_item_type(ItemType("child",
            dependant_ref=Reference("dependant"),
            name=Property("basic_string", required=True)
        ))
        self.manager.register_item_type(ItemType("dependant",
            name=Property("basic_string", required=True)
        ))

        root = self.manager.create_root_item("root")
        child = self.manager.create_item("child", "/my_child",
                                         name="child")
        dependant = self.manager.create_item("dependant", "/my_dependant",
            name="depend1")
        dependant_ref = self.manager.create_inherited(
            dependant.get_vpath(),
            "/my_child/dependant_ref")

        self.assertEqual(root, child.parent)
        self.assertEqual(root.my_child, child)
        self.assertEqual(root, dependant.parent)
        self.assertEqual(child, dependant_ref.parent)

    def test_parent_child_relationship_2(self):
        self.manager.register_item_type(ItemType("root",
            my_child=Child("child"),
            my_dependant=Child("dependant"),
            name=Property("basic_string")
        ))
        self.manager.register_item_type(ItemType("child",
            dependant_ref=Reference("dependant"),
            name=Property("basic_string", required=True)
        ))
        self.manager.register_item_type(ItemType("dependant",
            name=Property("basic_string", required=True)
        ))

        root = self.manager.create_root_item("root")
        child = self.manager.create_item("child", "/my_child",
                                         name="child")
        dependant = self.manager.create_item("dependant", "/my_dependant",
            name="depend1")
        dependant_ref = self.manager.create_inherited(
            dependant.get_vpath(),
            "/my_child/dependant_ref")

        self.assertEqual(root, child.parent)
        self.assertEqual(root.my_child, child)
        self.assertEqual(root, dependant.parent)
        self.assertEqual(child, dependant_ref.parent)

    def test_vpath(self):
        self.manager.register_item_type(ItemType("root",
            my_child=Child("child"),
            my_dependant=Child("dependant"),
            name=Property("basic_string")
        ))
        self.manager.register_item_type(ItemType("child",
            dependant_ref=Reference("dependant"),
            name=Property("basic_string", required=True)
        ))
        self.manager.register_item_type(ItemType("dependant",
            name=Property("basic_string", required=True)
        ))

        root = self.manager.create_root_item("root")
        child = self.manager.create_item("child", "/my_child",
                                         name="child")
        dependant = self.manager.create_item("dependant", "/my_dependant",
            name="depend1")
        dependant_ref = self.manager.create_inherited(
            dependant.get_vpath(),
            "/my_child/dependant_ref")

        self.assertEqual("/my_child", child.get_vpath())
        self.assertEqual("/my_dependant", dependant.get_vpath())
        self.assertEqual("/my_child/dependant_ref",
            dependant_ref.get_vpath())

    def test_vpath_2(self):
        self.manager.register_item_type(ItemType("root",
            my_child=Child("child"),
            my_dependant=Child("dependant"),
            name=Property("basic_string")
        ))
        self.manager.register_item_type(ItemType("child",
            dependant_ref=Reference("dependant"),
            name=Property("basic_string", required=True)
        ))
        self.manager.register_item_type(ItemType("dependant",
            name=Property("basic_string", required=True)
        ))

        root = self.manager.create_root_item("root")
        child = self.manager.create_item("child",
                                         "/my_child",
                                         name="child")
        dependant = self.manager.create_item("dependant",
                                             "/my_dependant",
                                             name="depend1")
        dependant_ref = self.manager.create_inherited(
            dependant.get_vpath(),
            "/my_child/dependant_ref")

        self.assertEqual("/my_child", child.get_vpath())
        self.assertEqual("/my_dependant", dependant.get_vpath())
        self.assertEqual("/my_child/dependant_ref",
            dependant_ref.get_vpath())

    def test_non_existing_item(self):
        self.assertEqual(None, self.manager.get_item("/nonexistant"))

    def test_many_child(self):
        self.manager.register_item_type(ItemType("root",
            entity1=Child("entity"),
        ))
        self.manager.register_item_type(ItemType("entity",
            packages=Collection("package"),
            name=Property("basic_string"),
        ))
        self.manager.register_item_type(ItemType("package",
            name=Property("basic_string", required=True)
        ))

        self.manager.create_root_item("root")
        item = self.manager.create_item("entity", "/entity1")

        self.assertTrue(type(item.packages) is CollectionItem)
        self.manager.create_item("package", "/entity1/packages/wget",
            name="wget")

        self.assertEqual("package", item.packages.wget.item_type.item_type_id)
        self.assertEqual("wget", item.packages.wget.name)

        self.manager.create_item("package", "/entity1/packages/vim",
            name="vim")

        self.assertEqual("package", item.packages.vim.item_type.item_type_id)
        self.assertEqual("vim", item.packages.vim.name)

    def test_many_child_2(self):
        self.manager.register_item_type(ItemType("root",
            entity1=Child("entity"),
        ))
        self.manager.register_item_type(ItemType("entity",
            packages=Collection("package"),
            name=Property("basic_string"),
        ))
        self.manager.register_item_type(ItemType("package",
            name=Property("basic_string", required=True)
        ))

        self.manager.create_root_item("root")
        item = self.manager.create_item("entity", "/entity1")

        self.assertTrue(type(item.packages) is CollectionItem)
        self.manager.create_item("package", "/entity1/packages/wget",
            name="wget")

        self.assertEqual("package", item.packages.wget.item_type.item_type_id)
        self.assertEqual("wget", item.packages.wget.name)

        self.manager.create_item("package", "/entity1/packages/vim",
            name="vim")

        self.assertEqual("package", item.packages.vim.item_type.item_type_id)
        self.assertEqual("vim", item.packages.vim.name)

    def test_setup_default_objects(self):
        self.manager.register_item_type(ItemType("root",
            my_child=Child("child"),
            my_dependant=Child("dependant"),
            entity1=Child("entity"),
        ))
        self.manager.register_item_type(ItemType("entity",
            name=Property("basic_string"),
            wget=Child("package", required=True),
        ))
        self.manager.register_item_type(ItemType("package",
            name=Property("basic_string", required=True),
            description=Property("basic_string", required=True,
                                 default="hello")
        ))

        self.manager.create_root_item("root")

        entity = self.manager.create_item("entity", "/entity1")

        self.assertEqual(None, entity.wget.name)
        self.assertEqual("hello", entity.wget.description)

    def test_setup_default_objects_2(self):
        self.manager.register_item_type(ItemType("root",
            my_child=Child("child"),
            my_dependant=Child("dependant"),
            entity1=Child("entity"),
        ))
        self.manager.register_item_type(ItemType("entity",
            name=Property("basic_string"),
            wget=Child("package", required=True),
        ))
        self.manager.register_item_type(ItemType("package",
            name=Property("basic_string", required=True),
            description=Property("basic_string", required=True,
                                 default="hello")
        ))

        self.manager.create_root_item("root")

        entity = self.manager.create_item("entity", "/entity1")

        self.assertEqual(None, entity.wget.name)
        self.assertEqual("hello", entity.wget.description)

    def test_ref_supertype(self):

        self.manager.register_item_type(ItemType("root",
            profiles=Collection("profile"),
            nodes=Collection("node"),
        ))
        self.manager.register_item_type(ItemType("profile",))
        self.manager.register_item_type(ItemType("os-profile",
            extend_item="profile",
            name=Property("basic_string")
        ))
        self.manager.register_item_type(ItemType("node",
            hostname=Property("basic_string"),
            is_locked=Property("basic_string", default="false"),
            os=Reference("profile"),
        ))

        self.manager.create_root_item("root")
        self.manager.create_item("node", "/nodes/node1",
            hostname="node1")
        self.manager.create_item("os-profile", "/profiles/os1",
            name="profile1")
        self.manager.create_inherited("/profiles/os1",
                                      "/nodes/node1/os")
        self.manager.update_item("/nodes/node1/os", name="other")

        self.assertEquals("os-profile",
            self.manager.get_item("/nodes/node1/os").item_type_id)

    def test_ref_collection_supertype(self):
        self.manager.register_item_type(ItemType("root",
            software=Collection("software-item"),
            nodes=Collection("node"),
        ))
        self.manager.register_item_type(ItemType("software-item",
        ))
        self.manager.register_item_type(ItemType("package",
            extend_item="software-item",
            name=Property("basic_string")
        ))
        self.manager.register_item_type(ItemType("node",
            hostname=Property("basic_string"),
            items=RefCollection("software-item"),
        ))

        self.manager.create_root_item("root")
        self.manager.create_item("node", "/nodes/node1",
            hostname="node1")
        self.manager.create_item("package", "/software/file",
            name="file")
        self.manager.create_inherited("/software/file",
                                      "/nodes/node1/items/file")

        self.assertEquals("package",
            self.manager.get_item("/nodes/node1/items/file").item_type_id)
        self.manager.update_item("/nodes/node1/items/file", name="other")

    def test_search(self):
        self.manager.register_item_type(ItemType("root",
            service1=Collection("clusteredservice"),
            nodes=Collection("node"),
            systems=Collection("system"),
            blades=Collection("blade"),
        ))
        self.manager.register_item_type(ItemType("clusteredservice",
            nodes=RefCollection("node"),
        ))
        self.manager.register_item_type(ItemType("node",
            hostname=Property("basic_string"),
            system=Reference("system"),
        ))
        self.manager.register_item_type(ItemType("system",
            name=Property("basic_string"),
            blade=Reference("blade"),
        ))
        self.manager.register_item_type(ItemType("blade",
            blade_type=Property("basic_string"),
        ))

        self.manager.create_root_item("root")
        self.manager.create_item("node", "/nodes/node1",
            hostname="node1.com")
        self.manager.create_item("node", "/nodes/node2",
            hostname="node2.com")
        self.manager.create_item("node", "/nodes/node3",
            hostname="node3.com")
        self.manager.create_item("system", "/systems/system1",
                                 name="sys1")
        self.manager.create_item("blade", "/blades/blade1",
                                 blade_type="hp1")

        self.manager.create_inherited("/systems/system1",
                                      "/nodes/node1/system")
        self.manager.create_inherited("/systems/system1",
                                      "/nodes/node2/system")
        self.manager.create_inherited("/systems/system1",
                                      "/nodes/node3/system")

        self.manager.create_inherited("/blades/blade1",
                                      "/systems/system1/blade")

        found = self.manager.query("system")

        self.assertEqual(1, len(found))

        self.assertEqual("system", found[0].item_type.item_type_id)

        node1 = QueryItem(self.manager,
                self.manager.query("node", hostname="node1.com")[0])
        self.assertEqual("node1.com", node1.hostname)
        self.assertEqual("sys1", node1.system.name)
        self.assertEqual("hp1", node1.system.blade.blade_type)
        node2 = self.manager.query("node", hostname="node2.com")[0]
        self.assertEqual("node2.com", node2.hostname)
        self.assertEqual("sys1", node1.system.name)
        self.assertEqual("hp1", node1.system.blade.blade_type)

    def test_validate(self):
        self.manager.register_item_type(ItemType("root",
            service1=Collection("clusteredservice"),
            nodes=Collection("node"),
            systems=Collection("system"),
            blades=Collection("blade"),
        ))
        self.manager.register_item_type(ItemType("clusteredservice",
            nodes=RefCollection("node"),
        ))
        self.manager.register_item_type(ItemType("node",
            hostname=Property("basic_string"),
            system=Reference("system"),
        ))
        self.manager.register_item_type(ItemType("system",
            name=Property("basic_string"),
            blade=Reference("blade"),
        ))
        self.manager.register_item_type(ItemType("blade",
            blade_type=Property("basic_string"),
        ))

        self.manager.create_root_item("root")
        self.manager.create_item("node", "/nodes/node1",
            hostname="node1.com")
        self.manager.create_item("node", "/nodes/node2",
            hostname="node2.com")
        self.manager.create_item("system", "/systems/system1",
                                 name="sys1")
        self.manager.create_item("blade", "/blades/blade1",
                                 blade_type="hp1")

        errors = self.manager.create_item("node", "/node1")
        self.assertEqual(type(errors), list)
        self.assertEqual(len(errors), 1)
        err = errors[0]
        self.assertEqual(err.error_type, 'ChildNotAllowedError')
        self.assertEqual(err.error_message,
            "'node1' (type: 'node') "
                    "is not an allowed child of /")

        errors = self.manager.create_item("blade",
                                            "/nodes/node1/system")
        self.assertEqual(type(errors), list)
        self.assertEqual(len(errors), 1)
        err = errors[0]
        self.assertEqual(err.error_type, 'InvalidChildTypeError')
        self.assertEqual(err.error_message,
                          "'blade' is not an allowed type for child 'system'")

        errors = self.manager.create_item("system", "/nodes/system1")
        self.assertEqual(type(errors), list)
        self.assertEqual(len(errors), 1)
        err = errors[0]
        self.assertEqual(err.error_type, 'InvalidChildTypeError')
        self.assertEqual(
            err.error_message,
           "'system' is not an allowed type for collection of item type 'node'"
        )

    def test_validate_extends(self):
        self.manager.register_item_type(ItemType("root",
            nodes=Collection("node"),
        ))
        self.manager.register_item_type(ItemType("node",
            hostname=Property("basic_string"),
            system=Child("system"),
        ))
        self.manager.register_item_type(ItemType("cmw-node",
            extend_item="node",))
        self.manager.register_item_type(ItemType("system",
            name=Property("basic_string"),
        ))
        self.manager.register_item_type(ItemType("hp-system",
            extend_item="system",))

        self.manager.create_root_item("root")
        self.manager.create_item("node", "/nodes/node1")
        self.manager.create_item("cmw-node", "/nodes/node2")
        self.assertEqual("cmw-node",
            self.manager.get_item("/nodes/node2")._item_type.item_type_id)

        self.manager.create_item("hp-system", "/nodes/node1/system")
        self.assertEqual("hp-system",
            self.manager.get_item("/nodes/node1/system").
                                                _item_type.item_type_id)

    def test_validate_extends_2(self):
        self.manager.register_item_type(ItemType("root",
            nodes=Collection("node"),
        ))
        self.manager.register_item_type(ItemType("node",
            hostname=Property("basic_string"),
            system=Child("system"),
        ))
        self.manager.register_item_type(ItemType("cmw-node",
            extend_item="node",))
        self.manager.register_item_type(ItemType("system",
            name=Property("basic_string"),
        ))
        self.manager.register_item_type(ItemType("hp-system",
            extend_item="system",))

        self.manager.create_root_item("root")
        self.manager.create_item("node", "/nodes/node1")
        self.manager.create_item("cmw-node", "/nodes/node2")
        self.assertEqual("cmw-node",
            self.manager.get_item("/nodes/node2")._item_type.item_type_id)

        self.manager.create_item("hp-system", "/nodes/node1/system")
        self.assertEqual("hp-system",
            self.manager.get_item("/nodes/node1/system").
                                                _item_type.item_type_id)

    def test_extend_with_custom_item(self):
        self.manager.register_item_type(ItemType("root",
            nodes=Collection("node"),
        ))
        self.manager.register_item_type(ItemType("node",
            system=Child("system"),
        ))
        self.manager.register_item_type(self.mock_node_type)

        self.manager.create_root_item("root")
        self.manager.create_item("node", "/nodes/node1")
        self.manager.create_item("mock-node", "/nodes/node2")
        item = self.manager.get_item("/nodes/node2")
        self.assertTrue("system" in item._item_type.structure)
        self.assertTrue("hostname" in item._item_type.structure)

    def test_validate_references(self):
        self.manager.register_item_type(ItemType("root",
            nodes=Collection("node"),
            system=Child("system"),
            notsystem=Child("notsystem"),
        ))
        self.manager.register_item_type(ItemType("node",
            hostname=Property("basic_string"),
            system=Reference("system"),))
        self.manager.register_item_type(ItemType("system",
            name=Property("basic_string"),))
        self.manager.register_item_type(ItemType("hp-system",
            extend_item="system",))
        self.manager.register_item_type(ItemType("notsystem",
            name=Property("basic_string"),))

        self.manager.create_root_item("root")
        self.manager.create_item("node", "/nodes/node1")
        hpsys1 = self.manager.create_item("hp-system", "/system",
            name="HP1")

        notsys1 = self.manager.create_item("notsystem", "/notsystem",
            name="NO1")

        link1 = self.manager.create_inherited(hpsys1.get_vpath(),
                                              "/nodes/node1/system")
        self.manager.create_item("node", "/nodes/node2")

        errors = self.manager.create_inherited(notsys1.get_vpath(),
                                           "/nodes/node2/system")
        self.assertEqual(type(errors), list)
        self.assertEqual(len(errors), 1)
        err = errors[0]
        self.assertEqual(err.error_type, 'InvalidChildTypeError')
        self.assertEqual(
            err.error_message,
            "'notsystem' is not an allowed type for child 'system'")

    def test_cant_add_same_child_twice(self):
        self.manager.register_item_type(ItemType("root",
            nodes=Collection("node"),
        ))
        self.manager.register_item_type(ItemType("node",
            hostname=Property("basic_string"),
            system=Child("system"),
        ))
        self.manager.register_item_type(ItemType("system",
            name=Property("basic_string"),
        ))
        self.manager.create_root_item("root")

        self.manager.create_item("node", "/nodes/node1")
        errors = self.manager.create_item("node", "/nodes/node1")
        self.assertEqual(1, len(errors))
        self.assertEqual("ItemExistsError", errors[0].error_type)

    def test_cannot_create_child_of_type_reference(self):
        self.manager.register_item_type(ItemType("root",
            nodes=Collection("node"),
            system=Child("system"),
        ))
        self.manager.register_item_type(ItemType("node",
            hostname=Property("basic_string"),
            system=Reference("system"),
        ))
        self.manager.register_item_type(ItemType("system",
            name=Property("basic_string"),
        ))
        self.manager.create_root_item("root")
        result = self.manager.create_item("node", "/nodes/node1")
        self.assertTrue(isinstance(result, ModelItem))
        result = self.manager.create_item("system",
                                            "/nodes/node1/system")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].to_dict()["uri"],
                          "/nodes/node1")
        self.assertEqual(result[0].to_dict()["message"],
                          "'system' must be an inherited item")
        self.assertEqual(result[0].to_dict()["error"],
                          "ChildNotAllowedError")

    def test_default_references(self):
        self.manager.register_item_type(ItemType("root",
            nodes=Collection("node"),
            systems=Collection("system"),
        ))
        self.manager.register_item_type(ItemType("node",
            hostname=Property("basic_string"),
            system=Reference("system", default=True, name="mistersystem"),
        ))
        self.manager.register_item_type(ItemType("system",
            name=Property("basic_string"),
        ))
        self.manager.create_root_item("root")
        node = self.manager.create_item("node", "/nodes/node1")

        sys1 = self.manager.create_item("system", "/systems/system1",
            name="mistersystem")
        sys2 = self.manager.create_item("system", "/systems/system2",
            name="mrssystem")
        sys_link = self.manager.update_item("/nodes/node1/system",
                                            name='mistersystem')

    def test_update_reference(self):
        self.manager.register_item_type(ItemType("root",
            nodes=Collection("node"),
            systems=Collection("system"),
        ))
        self.manager.register_item_type(ItemType("node",
            hostname=Property("basic_string"),
            system=Reference("system"),
        ))
        self.manager.register_item_type(ItemType("system",
            name=Property("basic_string"),
        ))
        self.manager.create_root_item("root")
        node = self.manager.create_item("node", "/nodes/node1")

        sys1 = self.manager.create_item("system", "/systems/system1",
            name="mistersystem")

        link1 = self.manager.create_inherited(sys1.get_vpath(),
                                              "/nodes/node1/system")
        link1.update_properties({"name": "mrssystem"})

        self.assertEqual("mrssystem", link1.get_property("name"))

    def test_update_properties(self):
        self.manager.register_item_type(ItemType("root",
            nodes=Collection("node"),
            systems=Collection("system"),
        ))
        self.manager.register_item_type(ItemType("node",
            hostname=Property("basic_string"),
            system=Reference("system"),
        ))
        self.manager.register_item_type(ItemType("system",
            name=Property("basic_string"),
        ))
        self.manager.create_root_item("root")
        node = self.manager.create_item("node", "/nodes/node1")

        sys1 = self.manager.create_item("system", "/systems/system1",
            name="mistersystem")
        sys2 = self.manager.create_item("system", "/systems/system2",
            name="mrssystem")

        sys1 = self.manager.update_item("/systems/system1", name="another")

        self.assertEqual("another", sys1.get_property("name"))

        sys1 = self.manager.update_item("/systems/system1", name="yet_another")

    def test_update_non_config_properties(self):
        self.manager.register_item_type(ItemType("root",
            nodes=Collection("node"),
            systems=Collection("system"),
        ))
        self.manager.register_item_type(ItemType("node",
            hostname=Property("basic_string"),
            system=Reference("system"),
        ))
        self.manager.register_item_type(ItemType("system",
            config=Property("basic_string"),
            non_config=Property("basic_string", configuration=False),
        ))
        self.manager.create_root_item("root")
        node = self.manager.create_item("node", "/nodes/node1")

        sys1 = self.manager.create_item("system", "/systems/system1",
            config="config",
            non_config="non_config")
        self.manager.set_all_applied()
        sys1 = self.manager.get_item("/systems/system1")

        self.manager.update_item("/systems/system1", non_config="applied")
        self.assertEqual("applied", sys1.get_property("non_config"))
        self.assertEqual("Applied", sys1.get_state())

        self.manager.update_item("/systems/system1", config="updated")
        self.assertEqual("updated", sys1.get_property("config"))
        self.assertEqual("Updated", sys1.get_state())
        self.manager.update_item("/systems/system1", non_config="updated")
        self.assertEqual("updated", sys1.get_property("non_config"))
        self.assertEqual("Updated", sys1.get_state())

        self.manager.remove_item("/systems/system1")
        self.assertEqual("ForRemoval", sys1.get_state())
        self.manager.update_item("/systems/system1", non_config="for_removal")
        self.assertEqual("for_removal", sys1.get_property("non_config"))
        self.assertEqual("Updated", sys1.get_state())

    def test_update_properties_2(self):
        self.manager.register_item_type(ItemType("root",
            nodes=Collection("node"),
            systems=Collection("system"),
        ))
        self.manager.register_item_type(ItemType("node",
            hostname=Property("basic_string"),
            system=Reference("system"),
        ))
        self.manager.register_item_type(ItemType("system",
            name=Property("basic_string"),
        ))
        self.manager.create_root_item("root")
        node = self.manager.create_item("node", "/nodes/node1")

        sys1 = self.manager.create_item("system", "/systems/system1",
            name="mistersystem")
        sys2 = self.manager.create_item("system", "/systems/system2",
            name="mrssystem")

        sys1 = self.manager.update_item("/systems/system1", name="another")

        self.assertEqual("another", sys1.get_property("name"))

    def test_update_properties_required_2(self):
        self.manager.register_item_type(ItemType("root",
            propnodes=Collection("propnode")
        ))
        self.manager.register_item_type(ItemType("propnode",
            prop_required_default=Property("basic_string",
                                           required=True,
                                           default="123"),
            prop_required_no_default=Property("basic_string",
                                              required=True),
            prop_not_required_default=Property("basic_string",
                                               required=False,
                                               default="123"),
            prop_not_required_no_default=Property("basic_string")
        ))

        self.manager.create_root_item("root")
        item_path = "/propnodes/propnodeOK"
        self.manager.create_item("propnode", item_path,
                                   prop_required_default="11",
                                   prop_required_no_default="10",
                                   prop_not_required_no_default="00",
                                   prop_not_required_default="01")

        updates = {"prop_required_default": None}
        result1 = self.manager.update_item(item_path, **updates)
        # prop_required_default will reset to its default value
        self.assertTrue(type(result1), type(ModelItem))
        self.assertEqual(result1.prop_required_default, "123")

        updates = {"prop_required_no_default": None}
        result2 = self.manager.update_item(item_path, **updates)
        self.assertTrue(result2 is not None, "validation error expected")

        updates = {"prop_not_required_no_default": None}
        result3 = self.manager.update_item(item_path, **updates)
        self.assertTrue(type(result3), type(ModelItem))
        self.assertEqual(result3.prop_not_required_no_default, None)

        updates = {"prop_not_required_default": None}
        result4 = self.manager.update_item(item_path, **updates)
        self.assertTrue(type(result4), type(ModelItem))
        self.assertEqual(result4.prop_not_required_default, '123')

        updates = {"invalid_prop": 'bogey'}
        invalid_prop_result = self.manager.update_item(item_path, **updates)
        self.assertEqual(len(invalid_prop_result), 1)
        self.assertEqual(invalid_prop_result[0],
                         ValidationError(
                                        property_name="invalid_prop",
                                        error_message='"invalid_prop" is not '
                                        'an allowed property of propnode',
                                        error_type="PropertyNotAllowedError"
                                        )
                         )

    def test_delete_properties(self):
        self.manager.register_item_type(ItemType("root",
            propnodes=Collection("propnode")
        ))
        self.manager.register_item_type(ItemType("propnode",
            prop_required_default=Property("basic_string",
                                           required=True,
                                           default="123"),
            prop_required_no_default=Property("basic_string",
                                              required=True),
            prop_not_required_default=Property("basic_string",
                                               required=False,
                                               default="123"),
            prop_not_required_no_default=Property("basic_string")
        ))

        self.manager.create_root_item("root")
        item_path = "/propnodes/propnodeOK"
        self.manager.create_item("propnode", item_path,
                                   prop_required_default="11",
                                   prop_required_no_default="10",
                                   prop_not_required_no_default="00",
                                   prop_not_required_default="01")

        updates = {"prop_required_default": None,
                   "prop_not_required_default": None,
                   "prop_not_required_no_default": None}
        result = self.manager.update_item(item_path, **updates)
        item = self.manager.get_item(item_path)
        self.assertEqual("10", item.properties["prop_required_no_default"])
        self.assertEqual("123", item.properties["prop_required_default"])
        self.assertEqual(None, item.properties.get("prop_not_required_no_default", None))
        updates = {"prop_required_default": None,
                   "prop_not_required_default": None,
                   "prop_not_required_no_default": "value"}
        result = self.manager.update_item(item_path, **updates)
        self.assertEqual("value", item.properties.get("prop_not_required_no_default", "value"))


    def test_update_item_2(self):
        self.manager.register_item_type(
            ItemType(
                "root", nodes=Collection("node"), systems=Collection("system"))
        )

        self.manager.register_item_type(
            ItemType("node", hostname=Property("special_string"))
        )

        self.manager.register_item_type(
            ItemType("system", name=Property("basic_string", required=True))
        )

        self.manager.create_root_item("root")
        node = self.manager.create_item("node", "/nodes/node1")

        sys1 = self.manager.create_item("system", "/systems/system1",
                                          name="sys1")

        sys2 = self.manager.create_item("system", "/systems/system2",
                                          name="sys2")

        # fail if item doesn't exist
        errors = self.manager.update_item("/nodes/node9", name="123")
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].error_type, constants.INVALID_LOCATION_ERROR)
        self.assertEqual(errors[0].error_message, "Path not found")

        # fail prop not allowed on update of node
        errors = self.manager.update_item("/nodes/node1", name="123")
        self.assertEquals(len(errors), 1)
        self.assertEquals(errors[0].property_name, 'name')
        self.assertEquals(errors[0].error_type, 'PropertyNotAllowedError')
        self.assertEquals(errors[0].error_message,
                          '"name" is not an allowed property of node')
        self.assertRaises(ValueError, node.get_property, "name")

        # fail invalid prop on update of node
        errors = self.manager.update_item("/nodes/node1",
                                            hostname="123")
        self.assertEqual(errors[0].property_name, 'hostname')
        self.assertEqual(errors[0].error_type, 'ValidationError')
        self.assertEqual(errors[0].error_message,
                          "Invalid value '123'.")
        self.assertEqual(None, node.get_property("hostname"))
        # successful update of node
        updated_node = self.manager.update_item("/nodes/node1",
                                                  hostname="abc")
        node = self.manager.get_item(node.vpath)
        self.assertTrue(isinstance(updated_node, ModelItem))
        self.assertEqual(updated_node, node)
        self.assertEqual("abc", node.get_property("hostname"))
        # successful update of system
        updated_sys1 = self.manager.update_item("/systems/system1",
                                             name="renamed_sys1")
        self.assertTrue(isinstance(updated_sys1, ModelItem))
        sys1 = self.manager.get_item(sys1.vpath)
        self.assertEqual(updated_sys1, sys1)
        self.assertEqual("renamed_sys1", sys1.get_property("name"))
        # failed (removing required prop) update of system
        errors = self.manager.update_item("/systems/system2", name=None)
        self.assertTrue(isinstance(errors, list))
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].property_name, 'name')
        self.assertEqual(errors[0].error_type, 'MissingRequiredPropertyError')
        self.assertEqual(errors[0].error_message, 'ItemType "system" is '
            'required to have a property with name "name"')
        self.assertEqual("sys2", sys2.get_property("name"))

    def test_delete(self):
        self.manager.register_item_type(ItemType("root",
            nodes=Collection("node"),
            systems=Collection("system"),
        ))
        self.manager.register_item_type(ItemType("node",
            hostname=Property("basic_string", default="node1.com"),
            system=Reference("system"),
            child=Child("nodechild"),
        ))
        self.manager.register_item_type(ItemType("nodechild",
            name=Property("basic_string"),
            subchild=Child("subchild"),
        ))
        self.manager.register_item_type(ItemType("system",
            name=Property("basic_string"),
            syschild=Child("syschild"),
        ))
        self.manager.register_item_type(ItemType("syschild",
            name=Property("basic_string"),
        ))
        self.manager.register_item_type(ItemType("subchild",
            name=Property("basic_string"),
        ))

        self.manager.create_root_item("root")
        self.manager.create_item("system", "/systems/sys1",
            name="sys1")
        self.manager.create_item("syschild", "/systems/sys1/syschild",
            name="Sys Child")

        self.manager.create_item("node", "/nodes/node1",
            hostname="node1")
        self.manager.create_item("nodechild", "/nodes/node1/child",
            name="VonderKind")
        self.manager.create_item("subchild",
                                 "/nodes/node1/child/subchild",
            name="UberVonderKind")
        self.manager.create_inherited("/systems/sys1",
                                      "/nodes/node1/system")

        node = self.manager.query("node", hostname="node1")[0]

        self.manager.set_all_applied()

        self.manager.remove_item("/nodes/node1/child")

        self.assertEqual("ForRemoval", node.child.get_state())
        self.assertEqual("ForRemoval", node.child.subchild.get_state())

        self.manager.remove_item("/nodes/node1/system")

        self.assertEqual("ForRemoval", node.system.get_state())
        self.assertEqual("ForRemoval", node.system.syschild.get_state())

    def test_delete_2(self):
        self.manager.register_item_type(ItemType("root",
            nodes=Collection("node"),
            systems=Collection("system"),
        ))
        self.manager.register_item_type(ItemType("node",
            hostname=Property("basic_string", default="node1.com"),
            system=Reference("system"),
            child=Child("nodechild"),
        ))
        self.manager.register_item_type(ItemType("nodechild",
            name=Property("basic_string"),
        ))
        self.manager.register_item_type(ItemType("system",
            name=Property("basic_string"),
            syschild=Child("syschild"),
        ))
        self.manager.register_item_type(ItemType("syschild",
            name=Property("basic_string"),
        ))

        self.manager.create_root_item("root")
        self.manager.create_item("system", "/systems/sys1",
            name="sys1")
        self.manager.create_item("syschild", "/systems/sys1/syschild",
            name="Sys Child")

        self.manager.create_item("node", "/nodes/node1",
            hostname="node1")
        self.manager.create_item("nodechild", "/nodes/node1/child",
            name="VonderKind")
        self.manager.create_inherited("/systems/sys1",
                                      "/nodes/node1/system")

        node = self.manager.query("node", hostname="node1")[0]
        self.manager.set_all_applied()

        self.manager.remove_item("/nodes/node1/child")

        self.assertEqual("ForRemoval", node.child.get_state())

        self.manager.remove_item("/nodes/node1/system")

        self.assertEqual("ForRemoval", node.system.get_state())
        self.assertEqual("ForRemoval", node.system.syschild.get_state())

        validation_error = self.manager.remove_item("/")[0].to_dict()
        self.assertEqual(validation_error['uri'], '/')
        self.assertEqual(validation_error['message'],
                    constants.ERROR_MESSAGE_CODES.get(
                    constants.METHOD_NOT_ALLOWED_ERROR),
                    "Shouldn't be able delete root")
        self.assertEqual(validation_error['error'],
                          'MethodNotAllowedError',
                          "Expected MethodNotAllowedError")

    def test_deletion_of_sshd_configs(self):
        self.manager.register_item_type(ItemType("root",
            configs=Collection("sshd-config")
        ))

        self.manager.register_item_type(ItemType("sshd-config",
            permit_root_login=Property("basic_boolean", default="true"),
        ))

        self.manager.create_root_item("root")
        self.manager.create_item("sshd-config", "/configs/sshd_config")

        self.manager.set_all_applied()

        config = self.manager.query("sshd-config")

        validation_error = self.manager.remove_item("/configs/sshd_config")[0].to_dict()
        self.assertEqual(validation_error['uri'], '/configs/sshd_config')
        self.assertEqual(validation_error['message'],
                    constants.ERROR_MESSAGE_CODES.get(
                    constants.METHOD_NOT_ALLOWED_ERROR))
        self.assertEqual('MethodNotAllowedError', validation_error['error'])

        self.manager.create_item("sshd-config", "/configs/another_sshd_config")

        initial_config = [conf for conf in self.manager.query("sshd-config")
                        if conf.get_state() == "Initial"]

        self.assertEqual("/configs/another_sshd_config", initial_config[0].get_vpath())
        retval = self.manager.remove_item("/configs/another_sshd_config")
        self.assertEqual("Removed", retval.get_state())

    def test_delete_cascade_empty_collections(self):
        self.manager.register_item_type(ItemType("root",
            foo=Child("foo"),
        ))
        self.manager.register_item_type(ItemType("foo",
            bar=Child("bar"),
            items=Collection("bar"),
            refs=RefCollection("bar"),
        ))
        self.manager.register_item_type(ItemType("bar"))

        self.manager.create_root_item("root")
        foo = self.manager.create_item("foo", "/foo")
        bar = self.manager.create_item("bar", "/foo/bar")

        items = self.manager.get_item("/foo/items")
        refs = self.manager.get_item("/foo/refs")

        foo.set_applied()

        items = self.manager.remove_item("/foo")
        refs = self.manager.get_item("/foo/refs")

        self.assertTrue(items.is_for_removal())
        self.assertTrue(refs.is_for_removal())

    def test_cannot_remove_non_existing_item(self):
        validation_error = self.manager.remove_item("/blah")[0].to_dict()
        self.assertEqual(validation_error['uri'], '/blah')
        self.assertEqual(validation_error['message'], 'Path not found')
        self.assertEqual(validation_error['error'], constants.INVALID_LOCATION_ERROR)

    def test_property_types(self):
        self.manager.register_item_type(ItemType("root",
            nodes=Collection("node"),
        ))
        self.manager.register_item_type(ItemType("node",
            hostname=Property("special_string"),
        ))

        self.manager.create_root_item("root")
        errors = self.manager.create_item("node", "/nodes/node1",
                                     hostname="hn1")
        self.assertEqual(1, len(errors))
        error = errors[0].to_dict()
        self.assertEqual("ValidationError", error["error"])
        self.assertEqual(
            "Invalid value 'hn1'.",
            error["message"]
        )

    def test_validate_fails_for_property_not_allowed(self):
        self.manager.register_item_type(ItemType("root",
            nodes=Collection("node"),
        ))

        self.manager.register_item_type(ItemType("node",
            hostname=Property("basic_string"),
        ))

        self.manager.create_root_item("root")

        errors = self.manager.create_item("node", "/nodes/node1",
                                     hostname="hn1", wrong_prop="not_allowed")

        self.assert_(len(errors) > 0, "should contain one error")
        self.assertEqual(errors[0].to_dict()["error"],
                          "PropertyNotAllowedError")
        self.assertEqual(errors[0].to_dict()["message"],
                          '"wrong_prop" is not an allowed property '
                          'of node')

    def test_allow_multiple_references(self):
        self.manager.register_item_type(ItemType("root",
            refs=Collection("ref-item"),
            link_1=Reference("ref-item"),
            link_2=Reference("ref-item")
        ))
        self.manager.register_item_type(ItemType("ref-item",
            name=Property("basic_string", required=True)
        ))

        root = self.manager.create_root_item("root")
        ref1 = self.manager.create_item("ref-item", "/refs/ref1",
                                        name="ref1")

        link_1 = self.manager.create_inherited(ref1.get_vpath(),
                                               "/link_1")
        link_2 = self.manager.create_inherited(ref1.get_vpath(),
                                               "/link_2")

        self.assertEqual(len(self.manager.validate_model()), 0)

    def test_allow_multiple_references_2(self):
        self.manager.register_item_type(ItemType("root",
            refs=Collection("ref-item"),
            link_1=Reference("ref-item"),
            link_2=Reference("ref-item")
        ))
        self.manager.register_item_type(ItemType("ref-item",
            name=Property("basic_string", required=True)
        ))

        root = self.manager.create_root_item("root")
        ref1 = self.manager.create_item("ref-item", "/refs/ref1",
                                        name="ref1")

        link_1 = self.manager.create_inherited(ref1.get_vpath(),
                                               "/link_1")
        link_2 = self.manager.create_inherited(ref1.get_vpath(),
                                               "/link_2")

        self.assertEqual(len(self.manager.validate_model()), 0)

    def test_validate_collection_min_count(self):
        self.manager.register_item_type(ItemType('root',
            refs=Collection('ref-item', min_count=2)
        ))

        self.manager.register_item_type(ItemType('ref-item',
            name=Property('basic_string', required=True)
        ))

        root = self.manager.create_root_item("root")
        ref1 = self.manager.create_item('ref-item', '/refs/ref1',
                                        name='ref1')

        validation_errors = self.manager.validate_model()

        self.assertEqual(len(validation_errors), 1)

        val_err = validation_errors[0].to_dict()
        self.assertEqual(val_err['uri'], '/refs')
        self.assertEqual(
            val_err['message'],
            'This collection requires a minimum of 2 items not marked for '
            'removal')
        self.assertEqual(val_err['error'], 'CardinalityError')

        ref2 = self.manager.create_item('ref-item', '/refs/ref2',
                                        name='ref2')

        validation_errors = self.manager.validate_model()
        self.assertEqual(0, len(validation_errors))

    def test_validate_collection_min_count_2(self):
        self.manager.register_item_type(ItemType('root',
            refs=Collection('ref-item', min_count=2)
        ))

        self.manager.register_item_type(ItemType('ref-item',
            name=Property('basic_string', required=True)
        ))

        root = self.manager.create_root_item("root")
        ref1 = self.manager.create_item('ref-item', '/refs/ref1',
                                        name='ref1')

        validation_errors = self.manager.validate_model()

        self.assertEqual(1, len(validation_errors))

        val_err = validation_errors[0].to_dict()
        self.assertEqual(val_err['uri'], '/refs')
        self.assertEqual(
            val_err['message'],
            'This collection requires a minimum of 2 items'
            ' not marked for removal')
        self.assertEqual(val_err['error'], 'CardinalityError')

        ref2 = self.manager.create_item('ref-item', '/refs/ref2',
                                        name='ref2')

        validation_errors = self.manager.validate_model()
        self.assertEqual(len(validation_errors), 0)

    def test_validate_refcollection_min_count_not_removed(self):
        self.manager.register_item_type(ItemType('root',
            items=Collection('item', min_count=1),
            refitem=Child('ref-item')

        ))
        self.manager.register_item_type(ItemType('item',
            refs=RefCollection('ref-item', min_count=2)
        ))

        self.manager.register_item_type(ItemType('ref-item',
            name=Property('basic_string', required=True)
        ))

        root = self.manager.create_root_item("root")
        item = self.manager.create_item('item', '/items/item1')
        refitem = self.manager.create_item('ref-item',
                    '/refitem', name='ref1')
        ref1 = self.manager.create_inherited(refitem.get_vpath(),
                '/items/item1/refs/ref1')
        ref2 = self.manager.create_inherited(refitem.get_vpath(),
                '/items/item1/refs/ref2')

        validation_errors = self.manager.validate_model()
        self.assertEqual(0, len(validation_errors))

        self.manager.set_all_applied()

        self.manager.remove_item('/items/item1/refs/ref2')
        # validation does not account for removed items
        validation_errors = self.manager.validate_model()
        self.assertEqual(1, len(validation_errors))
        val_err = validation_errors[0].to_dict()
        self.assertEqual('/items/item1/refs', val_err['uri'])
        self.assertEqual(
            'This collection requires a minimum of 2 items not marked '
            'for removal',
            val_err['message'])
        self.assertEqual('CardinalityError', val_err['error'])

    def test_validate_collection_max_count(self):
        self.manager.register_item_type(ItemType('root',
            refs=Collection('ref-item', max_count=2)
        ))

        self.manager.register_item_type(ItemType('ref-item',
            name=Property('basic_string', required=True)
        ))

        root = self.manager.create_root_item("root")
        ref1 = self.manager.create_item('ref-item', '/refs/ref1',
                                        name='ref1')

        validation_errors = self.manager.validate_model()
        self.assertEqual(len(validation_errors), 0)

        ref2 = self.manager.create_item('ref-item', '/refs/ref2',
                                        name='ref2')
        ref3 = self.manager.create_item('ref-item', '/refs/ref3',
                                        name='ref3')

        validation_errors = self.manager.validate_model()

        self.assertEqual(len(validation_errors), 1)

        val_err = validation_errors[0].to_dict()
        self.assertEqual(val_err['uri'], '/refs')
        self.assertEqual(
            val_err['message'],
            'This collection is limited to a maximum of 2 items not marked '
            'for removal')
        self.assertEqual(val_err['error'], 'CardinalityError')

    def test_validate_collection_max_count_2(self):
        self.manager.register_item_type(ItemType('root',
            refs=Collection('ref-item', max_count=2)
        ))

        self.manager.register_item_type(ItemType('ref-item',
            name=Property('basic_string', required=True)
        ))

        root = self.manager.create_root_item("root")
        ref1 = self.manager.create_item('ref-item', '/refs/ref1',
                                        name='ref1')

        validation_errors = self.manager.validate_model()
        self.assertEqual(len(validation_errors), 0)

        ref2 = self.manager.create_item('ref-item', '/refs/ref2',
                                        name='ref2')
        ref3 = self.manager.create_item('ref-item', '/refs/ref3',
                                        name='ref3')

        validation_errors = self.manager.validate_model()

        self.assertEqual(len(validation_errors), 1)

        val_err = validation_errors[0].to_dict()
        self.assertEqual(val_err['uri'], '/refs')
        self.assertEqual(
            val_err['message'],
            'This collection is limited to a maximum of 2 items not marked '
            'for removal')
        self.assertEqual(val_err['error'], 'CardinalityError')

    def test_model_item_state(self):
        self.manager.register_item_type(ItemType("root",
            nodes=Collection("node"),
            systems=Collection("system"),
            profiles=Collection("os-profile"),
        ))
        self.manager.register_item_type(ItemType("node",
            hostname=Property("basic_string"),
            os=Reference("os-profile"),
        ))
        self.manager.register_item_type(ItemType("os-profile",
            name=Property("basic_string"),
            system=Reference("system"),
        ))
        self.manager.register_item_type(ItemType("system",
            name=Property("basic_string")
        ))

        root = self.manager.create_root_item("root")
        node = self.manager.create_item("node",
                                         "/nodes/node1",
                                         hostname="node1")
        system = self.manager.create_item("system",
                                             "/systems/sys1",
                                             name="sys1")
        os = self.manager.create_item("os-profile",
                                             "/profiles/os1",
                                             name="os1")
        self.manager.create_inherited(os.get_vpath(), "/nodes/node1/os")
        self.manager.create_inherited(system.get_vpath(),
                                      "/profiles/os1/system")

        self.assertEqual("Initial", root.get_state())
        self.assertEqual("Initial", node.get_state())
        self.assertEqual("Initial", system.get_state())
        self.assertEqual("Initial", os.get_state())

        self.manager.set_all_applied()

        root = self.manager.get_item(root.vpath)
        node = self.manager.get_item(node.vpath)
        system = self.manager.get_item(system.vpath)
        os = self.manager.get_item(os.vpath)
        self.assertEqual("Applied", root.get_state())
        self.assertEqual("Applied", node.get_state())
        self.assertEqual("Applied", system.get_state())
        self.assertEqual("Applied", os.get_state())

    def test_model_item_state_2(self):
        self.manager.register_item_type(ItemType("root",
            nodes=Collection("node"),
            systems=Collection("system"),
            profiles=Collection("os-profile"),
        ))
        self.manager.register_item_type(ItemType("node",
            hostname=Property("basic_string"),
            os=Reference("os-profile"),
        ))
        self.manager.register_item_type(ItemType("os-profile",
            name=Property("basic_string"),
            system=Reference("system"),
        ))
        self.manager.register_item_type(ItemType("system",
            name=Property("basic_string")
        ))

        root = self.manager.create_root_item("root")
        node = self.manager.create_item("node",
                                         "/nodes/node1",
                                         hostname="node1")
        system = self.manager.create_item("system",
                                             "/systems/sys1",
                                             name="sys1")
        os = self.manager.create_item("os-profile",
                                             "/profiles/os1",
                                             name="os1")
        self.manager.create_inherited(os.get_vpath(), "/nodes/node1/os")
        self.manager.create_inherited(system.get_vpath(),
                                      "/profiles/os1/system")

        self.assertEqual("Initial", root.get_state())
        self.assertEqual("Initial", node.get_state())
        self.assertEqual("Initial", system.get_state())
        self.assertEqual("Initial", os.get_state())

        self.manager.set_all_applied()
        root = self.manager.get_item(root.vpath)
        node = self.manager.get_item(node.vpath)
        system = self.manager.get_item(system.vpath)
        os = self.manager.get_item(os.vpath)

        self.assertEqual("Applied", root.get_state())
        self.assertEqual("Applied", node.get_state())
        self.assertEqual("Applied", system.get_state())
        self.assertEqual("Applied", os.get_state())

    def test_validate_required_reference_item(self):
        self.manager.register_item_type(ItemType("root",
            refs=Collection("ref-item"),
            link=Reference("ref-item", required=True, default=True),
        ))
        self.manager.register_item_type(ItemType("ref-item",
            name=Property("basic_string", required=True)
        ))
        root = self.manager.create_root_item("root")

        self.assertEqual(len(self.manager.validate_model()), 1)
        validation_error = self.manager.validate_model()[0].to_dict()
        self.assertEqual(validation_error['uri'], '/')
        self.assertEqual(validation_error['message'],
                         'ItemType "root" is required to have a "reference" '
                         'with name "link" and type "ref-item"')
        self.assertEqual(validation_error['error'], 'MissingRequiredItemError')

        ref1 = self.manager.create_item("ref-item", "/refs/ref1",
                                        name="ref1")
        link = self.manager.create_inherited(ref1.get_vpath(), "/link")

        self.assertEqual(len(self.manager.validate_model()), 0)

    def test_validate_required_reference_item_2(self):
        self.manager.register_item_type(ItemType("root",
            refs=Collection("ref-item"),
            link=Reference("ref-item", required=True, default=True),
        ))
        self.manager.register_item_type(ItemType("ref-item",
            name=Property("basic_string", required=True)
        ))
        root = self.manager.create_root_item("root")

        self.assertEqual(len(self.manager.validate_model()), 1)
        validation_error = self.manager.validate_model()[0].to_dict()
        self.assertEqual(validation_error['uri'], '/')
        self.assertEqual(validation_error['message'],
                         'ItemType "root" is required to have a "reference" '
                         'with name "link" and type "ref-item"')
        self.assertEqual(validation_error['error'], 'MissingRequiredItemError')

        ref1 = self.manager.create_item("ref-item", "/refs/ref1",
                                        name="ref1")
        link = self.manager.create_inherited(ref1.get_vpath(),
                                             "/link")

        self.assertEqual(len(self.manager.validate_model()), 0)

    def test_validate_required_child(self):
        self.manager.register_item_type(ItemType('root',
            refs=Collection('ref-item'),
            child=Child('ref-item', required=True),
        ))

        self.manager.register_item_type(ItemType('ref-item',
            name=Property('basic_string', required=True),
        ))

        root = self.manager.create_root_item("root")

        validation_errors = self.manager.validate_model()

        self.assertEqual(len(validation_errors), 1)
        validation_error = self.manager.validate_model()[0].to_dict()
        self.assertEqual(validation_error['property_name'], 'name')
        self.assertEqual(
            validation_error['message'],
            'ItemType "ref-item" is required to have a property with name '
            '"name"'
        )
        self.assertEqual(validation_error['error'],
                          'MissingRequiredPropertyError')

    def test_validate_required_reference(self):
        self.manager.register_item_type(ItemType('root',
            ref=Reference('ref-item', required=True, default=False),
            child=Child('ref-item'),
        ))
        self.manager.register_item_type(ItemType('ref-item',
            name=Property('basic_string', required=True),
        ))

        root = self.manager.create_root_item("root")
        child = self.manager.create_item('ref-item', '/child',
                                         name="test")

        validation_errors = self.manager.validate_model()

        self.assertEqual(len(validation_errors), 1)
        validation_error = self.manager.validate_model()[0].to_dict()
        self.assertEqual(validation_error['uri'], '/')
        self.assertEqual(
            validation_error['message'],
            'ItemType "root" is required to have a "reference" with name "ref"'
            ' and type "ref-item"'
        )
        self.assertEqual(validation_error['error'],
                          'MissingRequiredItemError')

    def test_query_item(self):
        self.manager.register_item_type(ItemType("root",
            nodes=Collection("node"),
            systems=Collection("system"),
        ))
        self.manager.register_item_type(ItemType("node",
            hostname=Property("basic_string"),
            system=Reference("system"),
        ))
        self.manager.register_item_type(ItemType("system",
            name=Property("basic_string"),
        ))
        self.manager.create_root_item("root")
        node_item = self.manager.create_item("node", "/nodes/node1",
            hostname="node1")

        sys1 = self.manager.create_item("system", "/systems/system1",
            name="mistersystem")

        query = self.manager.query("node", hostname="node1")

        node = query[0]
        self.assertTrue(node.is_initial())

        node.set_applied()

        self.assertTrue(node.is_applied())
        self.assertEqual("node1", node.properties['hostname'])
        self.assertEqual("node1", node.hostname)
        node_item = self.manager.get_item(node_item.vpath)
        self.assertEqual({"hostname": "node1"}, node_item._applied_properties)

        node_item.update_properties({'hostname': "node2"})

        node = self.manager.query_by_vpath(node.vpath)
        self.assertTrue(node.is_updated())
        self.assertTrue(node_item.is_updated())
        self.assertEqual({"hostname": "node1"}, node_item._applied_properties)

    def test_query_item_children(self):
        self.manager.register_item_type(ItemType("root",
            nodes=Collection("node"),
            systems=Collection("system"),
        ))
        self.manager.register_item_type(ItemType("node",
            hostname=Property("basic_string"),
            system=Reference("system"),
            os=Child("os-profile"),
        ))
        self.manager.register_item_type(ItemType("os-profile",
            name=Property("basic_string"),
        ))
        sys1 = self.manager.register_item_type(ItemType("system",
            name=Property("basic_string"),
        ))
        # Had to update root vpath as QueryItem.get_source() was breaking
        # for ''
        self.manager.create_root_item("root")
        node = self.manager.create_item("node", "/nodes/node1",
            hostname="node1")

        os1 = self.manager.create_item("os-profile", "/nodes/node1/os",
            name="rhel")
        sys1 = self.manager.create_item("system", "/systems/system1",
            name="mistersystem")

        syslink = self.manager.create_inherited(sys1.get_vpath(),
                                                "/nodes/node1/system")

        query = self.api.query("node", hostname="node1")
        qnode = query[0]
        self.assertEqual("node1", qnode.hostname)
        self.assertEqual(sys1, qnode.system.get_source()._model_item)
        self.assertEqual("mistersystem", qnode.system.name)

        self.assertEqual(os1, qnode.os._model_item)
        self.assertEqual("rhel", qnode.os.name)

    def test_query_item_state_override(self):
        self.manager.register_item_type(ItemType("root",
            nodes=Collection("node"),
            systems=Collection("system"),
            profiles=Collection("os-profile"),
        ))
        self.manager.register_item_type(ItemType("node",
            hostname=Property("basic_string"),
            system=Reference("system"),
            os=Reference("os-profile"),
        ))
        self.manager.register_item_type(ItemType("os-profile",
            name=Property("basic_string"),
            items=Collection("package"),
        ))
        self.manager.register_item_type(ItemType("package",
            name=Property("basic_string"),
        ))
        self.manager.register_item_type(ItemType("system",
            name=Property("basic_string"),
            macaddress=Property("basic_string"),
        ))
        self.manager.create_root_item("root")
        self.manager.create_item("os-profile", "/profiles/os1",
            name="rhel")
        self.manager.create_item("package", "/profiles/os1/items/p1",
            name="vim")

        self.manager.create_item("node", "/nodes/node1",
            hostname="node1")
        self.manager.create_inherited("/profiles/os1",
                                      "/nodes/node1/os")
        self.manager.create_item("system", "/systems/system1",
            name="sys1")
        self.manager.create_inherited("/systems/system1",
                                      "/nodes/node1/system")

        self.manager.set_all_applied()

        self.manager.create_item("system", "/systems/system2",
            name="sys2")
        self.manager.create_item("node", "/nodes/node2",
            hostname="node2")
        self.manager.create_inherited("/profiles/os1",
                                      "/nodes/node2/os")
        self.manager.create_inherited("/systems/system2",
                                      "/nodes/node2/system")

        node_query = self.api.query("node")
        node_query = [node for node in node_query if node.has_initial_dependencies()]
        self.assertEqual(1, len(node_query))

        node2 = node_query[0]
        self.assertEqual("node2", node2.hostname)

        self.assertTrue(node2.is_initial())
        self.assertTrue(node2.os.is_initial())
        self.assertTrue(node2.system.is_initial())
        self.assertTrue(node2.os.items.is_initial())
        self.assertTrue(node2.os.items.p1.is_initial())

    def test_change_ref_updated_query(self):
        self.manager.register_item_type(ItemType("root",
            nodes=Collection("node"),
            systems=Collection("system"),
            profiles=Collection("os-profile"),
        ))
        self.manager.register_item_type(ItemType("node",
            hostname=Property("basic_string"),
            system=Reference("system"),
            os=Reference("os-profile"),
        ))
        self.manager.register_item_type(ItemType("os-profile",
            name=Property("basic_string"),
            items=Collection("package"),
        ))
        self.manager.register_item_type(ItemType("package",
            name=Property("basic_string"),
        ))
        self.manager.register_item_type(ItemType("system",
            name=Property("basic_string"),
            macaddress=Property("basic_string"),
        ))
        self.manager.create_root_item("root")
        self.manager.create_item("os-profile", "/profiles/os1",
            name="rhel")
        self.manager.create_item("os-profile", "/profiles/os2",
            name="ubuntu")
        self.manager.create_item("package", "/profiles/os1/items/p1",
            name="vim")

        self.manager.create_item("node", "/nodes/node1",
            hostname="node1")
        self.manager.create_inherited("/profiles/os1",
                                      "/nodes/node1/os")
        self.manager.create_item("system", "/systems/system1",
            name="sys1")
        self.manager.create_inherited("/systems/system1",
                                      "/nodes/node1/system")

        self.manager.set_all_applied()

        self.manager.update_item("/nodes/node1/os", name="ubuntu")

        node1 = QueryItem(self.manager, self.manager.query("node")[0])

        self.assertTrue(node1.is_applied())
        self.assertTrue(node1.system.is_applied())
        self.assertTrue(node1.os.is_updated())
        self.assertTrue(node1.os.items.is_applied())
        # prolly should remove it completely but hey...
        self.assertFalse(node1.os.items.p1.is_for_removal())

        self.assertTrue(node1.has_updated_dependencies())
        self.assertFalse(node1.has_removed_dependencies())

    def test_remove_ref_updated_query(self):
        # TODO check again and probably remove whole TC
        self.manager.register_item_type(ItemType("root",
            nodes=Collection("node"),
            profiles=Collection("os-profile"),
        ))
        self.manager.register_item_type(ItemType("node",
            hostname=Property("basic_string"),
            os=Reference("os-profile"),
        ))
        self.manager.register_item_type(ItemType("os-profile",
            name=Property("basic_string"),
            items=Collection("package"),
        ))
        self.manager.register_item_type(ItemType("package",
            name=Property("basic_string"),
        ))
        self.manager.create_root_item("root")
        self.manager.create_item("os-profile", "/profiles/os1",
            name="rhel")
        self.manager.create_item("package", "/profiles/os1/items/p1",
            name="vim")

        self.manager.create_item("node", "/nodes/node1",
            hostname="node1")
        self.manager.create_inherited("/profiles/os1",
                                      "/nodes/node1/os")

        self.manager.set_all_applied()

        package = self.manager.get_item("/profiles/os1/items/p1")
        self.assertTrue(package.is_applied())

        # LITPCDS-12018: Remove applied source, source and inherited items ForRemoval
        self.manager.remove_item("/profiles/os1/items/p1") # source item

        package = self.manager.get_item("/profiles/os1/items/p1")
        self.assertTrue(package.is_for_removal())

        node1 = QueryItem(self.manager,
                self.manager.query("node")[0])

        self.assertTrue(node1.is_applied())
        self.assertTrue(node1.os.is_applied())
        self.assertFalse(node1.os.items.is_initial())
        self.assertTrue(node1.os.items.p1.is_for_removal()) # inherited item

        self.assertTrue(node1.has_removed_dependencies()) # inherited item ForRemoval

    def test_validate_required_reference_2(self):
        self.manager.register_item_type(ItemType('root',
            ref=Reference('ref-item', required=True, default=False),
            child=Child('ref-item'),
        ))
        self.manager.register_item_type(ItemType('ref-item',
            name=Property('basic_string', required=True),
        ))

        root = self.manager.create_root_item("root")
        child = self.manager.create_item('ref-item', '/child',
                                         name="test")

        # missing required item
        validation_errors = self.manager.validate_model()
        self.assertEqual(len(validation_errors), 1)
        validation_error = self.manager.validate_model()[0].to_dict()
        self.assertEqual(validation_error['uri'], '/')
        self.assertEqual(
            validation_error['message'],
            'ItemType "root" is required to have a "reference" with name "ref"'
            ' and type "ref-item"'
        )
        self.assertEqual(validation_error['error'], 'MissingRequiredItemError')

        # required item present
        ref = self.manager.create_inherited(child.get_vpath(), '/ref')
        validation_errors = self.manager.validate_model()
        self.assertEqual(len(validation_errors), 0)

       # required item present but set for removal
        ref.set_for_removal()
        validation_errors = self.manager.validate_model()
        self.assertEqual(len(validation_errors), 1)
        validation_error = self.manager.validate_model()[0].to_dict()
        self.assertEqual(validation_error['uri'], '/ref')
        self.assertEqual(
            validation_error['message'],
            "This item is required and cannot be removed"
        )
        self.assertEqual(validation_error['error'], 'MissingRequiredItemError')

    def test_register_item_type_structure(self):
        prop_type1 = PropertyType("basic_type1")
        prop_type2 = PropertyType("basic_type2")
        self.manager.register_property_type(prop_type1)
        self.manager.register_property_type(prop_type2)

        self.manager.register_item_type(ItemType("item",
            prop1=Property("basic_type1")
        ))
        self.manager.register_item_type(ItemType("item-extension",
            extend_item="item",
            prop2=Property("basic_type2")
        ))
        item_type = self.manager.item_types["item"]
        item_type_ext = self.manager.item_types["item-extension"]

        self.assertEqual(len(item_type.structure), 1)
        self.assertEqual(item_type.structure.keys()[0], 'prop1')
        self.assertEqual(item_type.structure.values()[0].prop_type,
                          prop_type1)

        self.assertEqual(len(item_type_ext.structure), 2)
        self.assertTrue('prop1' in item_type_ext.structure.keys())
        self.assertEqual(item_type_ext.structure['prop1'].prop_type,
                          prop_type1)
        self.assertTrue('prop2' in item_type_ext.structure.keys())
        self.assertEqual(item_type_ext.structure['prop2'].prop_type,
                          prop_type2)

    def test_register_item_type_no_property_type(self):
        try:
            self.manager.register_item_type((ItemType("item",
                                     prop=Property("not_registered")))
                           )
        except Exception, e:
            self.assertEqual("Error registering itemtype \"item\"- property"
                             " type \"not_registered\" not yet registered",
                             str(e))

    def test_register_item_type_no_extend_item_type(self):
        try:
            self.manager.register_item_type(ItemType("item",
                                            extend_item="not_registered")
                                            )
        except Exception, e:
            self.assertEqual("Error registering itemtype \"item\"- base"
                             " type \"'not_registered'\" not yet registered",
                             str(e))

    def test_extend_no_property_overwrite(self):
        self.manager.register_item_type(ItemType("A-type",
                item_description="Base ItemType for Alphabet Items",
                item_name=Property("basic_string"),
            ))
        self.manager.register_item_type(ItemType("B-type",
                extend_item="A-type",
                item_description="An implementation of Alphabet Items",
                alphabet_type=Property("basic_string"),
            ))
        self.manager.register_item_type(ItemType("C-type",
                extend_item="B-type",
                item_description="An even more specific implementation of alphabet items",
                alphabet_options=Property("basic_string"),
            ))
        self.assertEquals(3, len(self.manager.item_types))
        self.assertEquals(1, len(self.manager.item_types['A-type'].structure))
        self.assertEquals(2, len(self.manager.item_types['B-type'].structure))
        self.assertEquals(3, len(self.manager.item_types['C-type'].structure))

        self.assertEquals(
            self.manager.item_types['A-type'].structure['item_name'],
            self.manager.item_types['B-type'].structure['item_name'])

    def test_extended_property_type_in_extended_item(self):
        class ExtendedProperty(Property):
            pass

        self.manager.register_item_type(ItemType("A-type",
                item_description="Base ItemType for Alphabet Items",
                item_name=ExtendedProperty("basic_string"),
            ))
        self.manager.register_item_type(ItemType("B-type",
                extend_item="A-type",
                item_description="An implementation of Alphabet Items",
                alphabet_type=ExtendedProperty("basic_string"),
            ))

        self.assertEquals(2, len(self.manager.item_types))
        self.assertEquals(1, len(self.manager.item_types['A-type'].structure))
        self.assertEquals(2, len(self.manager.item_types['B-type'].structure))

        self.assertFalse(self.manager.item_types['A-type'].structure['item_name'].prop_type is None)

    def test_get_get_plugin_updatable_items(self):
        self.manager.register_item_type(ItemType("root",
            software=Child("software", required=True),
            deployments=Collection("deployment"),
        ))
        self.manager.register_item_type(ItemType("deployment",
            nodes=Collection("node"),
        ))
        self.manager.register_item_type(ItemType("software",
            items=Collection("package"),
        ))

        # Items of type "package" may potentially be updated during plan
        # execution
        self.manager.register_item_type(ItemType("package",
            name=Property("basic_string"),
            updatable_prop=Property("basic_string", updatable_plugin=True)
        ))
        # This type inherits a plugin-updatable property from "package"
        self.manager.register_item_type(ItemType("specialised_package",
            extend_item="package",
            arch=Property("basic_string"),
        ))
        # Likewise, items of type "node" can be updated by CallbackTasks
        self.manager.register_item_type(ItemType("node",
            hostname=Property("basic_string", required=True),
            packages=RefCollection("package"),
        ))


        self.manager.create_root_item("root")
        source_item_a = self.manager.create_item(
            "package", "/software/items/package_a",
            name="scute", updatable_prop="initial_value"
        )
        source_item_b = self.manager.create_item(
            "package", "/software/items/package_b",
            name="gpg", updatable_prop="foo"
        )
        source_item_c = self.manager.create_item(
            "specialised_package", "/software/items/package_c",
            name="gpg", updatable_prop="foo", arch="arm"
        )
        #
        self.manager.create_item(
            "deployment", "/deployments/d1",
        )
        self.manager.create_item(
            "node", "/deployments/d1/nodes/n1",
            hostname="node1",
        )
        self.manager.create_item(
            "node", "/deployments/d1/nodes/n2",
            hostname="node2",
        )
        #
        inherited_item_a = self.manager.create_inherited("/software/items/package_a",
            "/deployments/d1/nodes/n1/packages/a")
        inherited_item_c = self.manager.create_inherited("/software/items/package_c",
            "/deployments/d1/nodes/n2/packages/c")

        result = self.manager.get_plugin_updatable_items()
        self.assertEqual(
            set([
                source_item_a.vpath,
                source_item_b.vpath,
                source_item_c.vpath,
                inherited_item_a.vpath,
                inherited_item_c.vpath,
            ]),
            result
        )

    def test_create_item_2(self):
        self.manager.register_item_type(
            ItemType("root", nodes=Collection("node"))
        )

        # create item with no registered item type
        result = self.manager.create_item("node", "/nodes/node1")
        self.assertTrue(isinstance(result, list))
        self.assertEqual(len(result), 1)
        err_dict = result[0].to_dict()
        self.assertEqual(err_dict["error"], "InvalidTypeError")
        self.assertEqual(err_dict["message"], "Item type not registered: node")
        self.assertEqual(err_dict["uri"], "/nodes/node1")

        self.manager.register_item_type(
            ItemType("node",
                     hostname=Property("basic_string", required=True),
                     system=Child("system"))
        )

        self.manager.register_item_type(
            ItemType("system", name=Property("basic_string"))
        )

        self.manager.create_root_item("root")

        # create item without required property
        result = self.manager.create_item("node", "/nodes/node1")
        self.assertTrue(isinstance(result, list))
        err_dict = result[0].to_dict()
        self.assertEqual(err_dict["error"], "MissingRequiredPropertyError")
        self.assertEqual(
            err_dict["message"],
            ('ItemType "node" is required to have a property with name '
            '"hostname"')
        )
        self.assertEqual(err_dict["property_name"], "hostname")

        # create a valid item
        result = self.manager.create_item("node",
                                            "/nodes/node1",
                                            hostname="my_name")
        self.assertTrue(not isinstance(result, list))

        # try to add duplicate child
        result = self.manager.create_item("node",
                                            "/nodes/node1",
                                            hostname="my_name")
        self.assertTrue(isinstance(result, list))
        self.assertEqual(len(result), 1)
        err_dict = result[0].to_dict()
        self.assertEqual(err_dict["error"], 'ItemExistsError')
        self.assertEqual(err_dict["message"],
                         "Item already exists in model: node1")
        self.assertEqual(err_dict["uri"], "/nodes/node1")

    def test_create_item_marked_for_removal_same_properties(self):
        self.manager.register_item_type(ItemType("root",
            services=Collection("clusteredservice"),
            nodes=Collection("node"),
            systems=Collection("system"),
            blades=Collection("blade")))
        self.manager.register_item_type(ItemType("clusteredservice",
            nodes=RefCollection("node")))
        self.manager.register_item_type(ItemType("node",
            hostname=Property("basic_string"),
            system=Reference("system")))
        self.manager.register_item_type(ItemType("system",
            name=Property("basic_string"), blade=Reference("blade")))
        self.manager.register_item_type(ItemType("blade",
            blade_type=Property("basic_string")))
        self.manager.create_root_item("root")

        service = self.manager.create_item("clusteredservice",
            "/services/service1")
        self.assertEqual(0, len(service.nodes))
        node = self.manager.create_item("node", "/nodes/node1",
            hostname="node1.com")
        node_link = self.manager.create_inherited("/nodes/node1",
            "/services/service1/nodes/node1")
        self.assertEqual(1, len(service.nodes))
        self.assertEqual("node1.com",
                         QueryItem(self.manager, self.manager.query_by_vpath(
                             node_link.get_vpath())).hostname)

        node.set_applied()
        node = self.manager.remove_item(node.get_vpath())

        self.assertEqual("ForRemoval", node.get_state())
        self.assertEqual("Removed", node_link.get_state())

        node = self.manager.create_item("node", "/nodes/node1",
            hostname="node1.com")
        node_link = self.manager.create_inherited("/nodes/node1",
            "/services/service1/nodes/node1")

        self.assertEqual("Applied", node.get_state())
        self.assertEqual("Initial", node_link.get_state())

    def test_create_item_marked_for_removal_different_properties(self):
        self.manager.register_item_type(ItemType("root",
            services=Collection("clusteredservice"),
            nodes=Collection("node"),
            systems=Collection("system"),
            blades=Collection("blade")))
        self.manager.register_item_type(ItemType("clusteredservice",
            nodes=RefCollection("node")))
        self.manager.register_item_type(ItemType("node",
            hostname=Property("basic_string"),
            system=Reference("system")))
        self.manager.register_item_type(ItemType("system",
            name=Property("basic_string"), blade=Reference("blade")))
        self.manager.register_item_type(ItemType("blade",
            blade_type=Property("basic_string")))
        self.manager.create_root_item("root")

        service = self.manager.create_item("clusteredservice",
            "/services/service1")
        self.assertEqual(0, len(service.nodes))
        node = self.manager.create_item("node", "/nodes/node1",
            hostname="node1.com")
        node_link = self.manager.create_inherited(node.get_vpath(),
            "/services/service1/nodes/node1")
        self.assertEqual(1, len(service.nodes))
        self.assertEqual("node1.com",
                         QueryItem(self.manager, self.manager.query_by_vpath(
                             node_link.get_vpath())).hostname)
        node.set_applied()
        node = self.manager.remove_item(node.get_vpath())
        self.assertEqual("ForRemoval", node.get_state())
        self.assertEqual("Removed", node_link.get_state())
        node = self.manager.create_item("node",
                "/nodes/node1",
                hostname="node1_changed.com")
        node_link = self.manager.create_inherited(
            node.get_vpath(),
            "/services/service1/nodes/node1")

        self.assertEqual("Updated", node.get_state())
        self.assertEqual("Initial", node_link.get_state())

        self.assertEquals("node1_changed.com", node.get_property("hostname"))

    def test_remove_all_removed(self):
        self.manager.register_item_type(ItemType("root",
            software=Child("software", required=True),
            deployments=Child("deployments", required=True, require="ms"),
            ms=Child("node", required=True),
        ))
        self.manager.register_item_type(ItemType("deployments",
            nodes=Collection("node"),
        ))
        self.manager.register_item_type(ItemType("node",
            hostname=Property("basic_string", required=True),
            os=Reference("os-profile"),
            packages=RefCollection("package"),
        ))
        self.manager.register_item_type(ItemType("software",
            profiles=Collection("os-profile"),
            items=Collection("package"),
        ))
        self.manager.register_item_type(ItemType("os-profile",
            name=Property("basic_string"),
        ))
        self.manager.register_item_type(ItemType("package",
            name=Property("basic_string"),
        ))

        root = self.manager.create_root_item("root")
        rhel = self.manager.create_item("os-profile", "/software/profiles/rhel",
            name="rhel")
        vim = self.manager.create_item("package", "/software/items/vim",
            name="vim")
        wget = self.manager.create_item("package", "/software/items/wget",
            name="wget")
        node1 = self.manager.create_item("node", "/deployments/nodes/node1",
            hostname="node1")
        self.manager.create_inherited(vim.get_vpath(),
                                      "/deployments/nodes/node1/packages/vim")
        self.manager.create_inherited(rhel.get_vpath(),
                                      "/deployments/nodes/node1/os")
        node2 = self.manager.create_item("node", "/deployments/nodes/node2",
                                         hostname="node2")
        self.manager.create_inherited(wget.get_vpath(),
                                      "/deployments/nodes/node2/packages/wget")
        self.manager.create_inherited(rhel.get_vpath(),
                                      "/deployments/nodes/node2/os")
        self.manager.create_inherited(vim.get_vpath(), "/ms/packages/vim")
        self.manager.create_inherited(wget.get_vpath(), "/ms/packages/wget")


        ms_model_item = self.manager.query_by_vpath("/ms")
        ms_model_item.set_removed()
        for pkg in ms_model_item.packages:
            pkg.set_removed()
        ms_model_item.packages.set_removed()


        node2_model_item = self.manager.query_by_vpath("/deployments/nodes/node2")
        node2_model_item.set_for_removal()
        node2_model_item.packages.set_removed()

        self.manager.delete_removed_items_after_plan()

        # The MS item has been fully removed from the model
        self.assertRaises(ModelManagerException, self.manager.query_by_vpath, "/ms")

        # node2.packages was reset to node2's state (ForRemoval)
        self.assertTrue(node2_model_item.packages.is_for_removal())
        self.assertTrue(node2_model_item.is_for_removal())

    def test_removed_referenced_item(self):
        self.manager.register_item_type(ItemType("root",
            software=Child("software", required=True),
            deployments=Child("deployments", required=True, require="ms"),
            ms=Child("node", required=True),
        ))
        self.manager.register_item_type(ItemType("deployments",
            nodes=Collection("node"),
        ))
        self.manager.register_item_type(ItemType("node",
            hostname=Property("basic_string", required=True),
            os=Reference("os-profile"),
            packages=RefCollection("package"),
        ))
        self.manager.register_item_type(ItemType("software",
            profiles=Collection("os-profile"),
            items=Collection("package"),
        ))
        self.manager.register_item_type(ItemType("os-profile",
            name=Property("basic_string"),
        ))
        self.manager.register_item_type(ItemType("package",
            name=Property("basic_string"),
        ))

        root = self.manager.create_root_item("root")
        rhel = self.manager.create_item("os-profile", "/software/profiles/rhel",
            name="rhel")
        vim = self.manager.create_item("package", "/software/items/vim",
            name="vim")
        wget = self.manager.create_item("package", "/software/items/wget",
            name="wget")
        node1 = self.manager.create_item("node", "/deployments/nodes/node1",
            hostname="node1")
        self.manager.create_inherited(vim.get_vpath(),
            "/deployments/nodes/node1/packages/vim")
        self.manager.create_inherited(rhel.get_vpath(),
                                 "/deployments/nodes/node1/os")
        node2 = self.manager.create_item("node", "/deployments/nodes/node2",
            hostname="node2")
        self.manager.create_inherited(wget.get_vpath(),
            "/deployments/nodes/node2/packages/wget")
        self.manager.create_inherited(rhel.get_vpath(),
                                 "/deployments/nodes/node2/os")
        self.manager.create_inherited(vim.get_vpath(), "/ms/packages/vim")
        self.manager.create_inherited(wget.get_vpath(), "/ms/packages/wget")

        self.manager.set_all_applied()

        # LITPCDS-12018: Removing applied source, ForRemoval source and inherited items
        self.manager.remove_item("/software/items/vim")

        self.assertEqual("ForRemoval",
                         self.manager.get_item("/software/items/vim").get_state())
        self.assertEqual("ForRemoval", self.manager.get_item("/deployments/nodes/node1/packages/vim").get_state())
        self.assertEqual("ForRemoval", self.manager.get_item("/ms/packages/vim").get_state())

        self.assertEqual("ForRemoval", self.manager.query_by_vpath("/software/items/vim").get_state())
        self.assertEqual("ForRemoval", self.manager.query_by_vpath("/deployments/nodes/node1/packages/vim").get_state())
        self.assertEqual("ForRemoval", self.manager.query_by_vpath("/ms/packages/vim").get_state())

        self.manager.delete_removed_items_after_plan()

        self.assertTrue(self.manager.get_item("/software/items/vim"))
        self.assertTrue(self.manager.get_item(
            "/deployments/nodes/node1/packages/vim"))
        self.assertTrue(self.manager.get_item("/ms/packages/vim"))

    def test_query_by_vpath(self):
        self.manager.register_item_type(ItemType("root",
            software=Child("software", required=True),
            deployments=Child("deployments", required=True, require="ms"),
            ms=Child("node", required=True),
        ))
        self.manager.register_item_type(ItemType("deployments",
            nodes=Collection("node"),
        ))
        self.manager.register_item_type(ItemType("node",
            hostname=Property("basic_string", required=True),
            os=Reference("os-profile"),
            packages=RefCollection("package"),
        ))
        self.manager.register_item_type(ItemType("software",
            profiles=Collection("os-profile"),
            items=Collection("package"),
        ))
        self.manager.register_item_type(ItemType("os-profile",
            name=Property("basic_string"),
        ))
        self.manager.register_item_type(ItemType("package",
            name=Property("basic_string"),
        ))

        root = self.manager.create_root_item("root")
        rhel = self.manager.create_item("os-profile",
            "/software/profiles/rhel", name="rhel")
        vim = self.manager.create_item("package", "/software/items/vim",
            name="vim")
        wget = self.manager.create_item("package", "/software/items/wget",
            name="wget")
        node1 = self.manager.create_item("node", "/deployments/nodes/node1",
            hostname="node1")
        self.manager.create_inherited("/software/items/vim",
            "/deployments/nodes/node1/packages/vim")
        node2 = self.manager.create_item("node", "/deployments/nodes/node2",
            hostname="node2")
        self.manager.create_inherited(
            "/software/items/vim", "/ms/packages/vim")

        node1_vim = QueryItem(self.manager, self.manager.query_by_vpath(
                                    "/deployments/nodes/node1/packages/vim"))
        self.assertEqual("vim", node1_vim.name)

        try:
            self.manager.query_by_vpath("/deployments/nonexistant/node1")
            self.fail("Should have thrown")
        except AssertionError:
            raise
        except Exception as e:
            self.assertEqual("Item /deployments/nonexistant/node1 not found", str(e))

    def test_update_with_same_value(self):
        self.manager.register_item_type(ItemType("root",
            nodes=Collection("node"),
        ))
        self.manager.register_item_type(ItemType("node",
            hostname=Property("basic_string", required=True),
        ))
        root = self.manager.create_root_item("root")
        node1 = self.manager.create_item("node", "/nodes/node1",
            hostname="node1")

        self.manager.set_all_applied()

        node1 = self.manager.get_item(node1.vpath)
        self.assertEquals("Applied", node1.get_state())

        node1 = self.manager.update_item("/nodes/node1", hostname="node1")

        self.assertEquals("Applied", node1.get_state())

    def test_delete_basic_structure(self):
        self.manager.register_item_type(ItemType(
            "root",
            softwares=Collection("item"),
            infrastructure=Child("infrastructure"),
        ))
        self.manager.register_item_type(ItemType(
            "item",
            name=Property("basic_string"),
        ))
        self.manager.register_item_type(ItemType(
            "infrastructure",
            storages=Collection("item"),
        ))
        self.manager.create_root_item("root")
        self.manager.create_item("item", "/software")
        self.manager.create_item("infrastructure", "/infrastructure")
        self.manager.create_item("item", "/infrastructure/storages")

        ret = self.manager.remove_item("/softwares")
        self.assertEquals(1, len(ret))
        error = ret[0]
        self.assertTrue(isinstance(error, ValidationError))
        self.assertEquals(constants.METHOD_NOT_ALLOWED_ERROR, error.error_type)
        self.assertEquals("/softwares", error.item_path)

        ret = self.manager.remove_item("/infrastructure")
        self.assertEquals(1, len(ret))
        error = ret[0]
        self.assertTrue(isinstance(error, ValidationError))
        self.assertEquals(constants.METHOD_NOT_ALLOWED_ERROR, error.error_type)
        self.assertEquals("/infrastructure", error.item_path)

        ret = self.manager.remove_item("/infrastructure/storages")
        self.assertEquals(1, len(ret))
        error = ret[0]
        self.assertTrue(isinstance(error, ValidationError))
        self.assertEquals(constants.METHOD_NOT_ALLOWED_ERROR, error.error_type)
        self.assertEquals("/infrastructure/storages", error.item_path)

        self.assertEquals(1, len(ret))
        error = ret[0]
        self.assertTrue(isinstance(error, ValidationError))
        self.assertEquals(constants.METHOD_NOT_ALLOWED_ERROR, error.error_type)
        self.assertEquals(1, len(ret))
        error = ret[0]
        self.assertTrue(isinstance(error, ValidationError))
        self.assertEquals(constants.METHOD_NOT_ALLOWED_ERROR, error.error_type)

    def test_has_parent_with_indeterminable_properties(self):
        self._create_simple_parent_child_structure()
        container = self.manager.get_item("/item")
        container._set_applied_properties_determinable(False)
        last_child = self.manager.get_item("/item/items/item1/items/item2")
        self.assertTrue(self.manager._has_ancestry_with_apd_false(last_child))
        container._set_applied_properties_determinable(True)
        self.assertFalse(self.manager._has_ancestry_with_apd_false(last_child))

    def test_remove_initial_parent_with_apd_false_collection_sub_items(self):
        # LITPCDS-9406: Don't remove container or its sub items if APD=False
        self._create_simple_parent_child_structure()
        container = self.manager.get_item("/item")
        container._set_applied_properties_determinable(False)
        self.manager.remove_item("/item")
        self.assertEqual(ModelItem.ForRemoval, container.get_state())
        sub_item = self.manager.get_item("/item/items")
        self.assertEqual(ModelItem.ForRemoval, sub_item.get_state())
        sub_item = self.manager.get_item("/item/items/item1")
        self.assertEqual(ModelItem.ForRemoval, sub_item.get_state())
        sub_item = self.manager.get_item("/item/items/item1/items")
        self.assertEqual(ModelItem.ForRemoval, sub_item.get_state())
        sub_item = self.manager.get_item("/item/items/item1/items/item2")
        self.assertEqual(ModelItem.ForRemoval, sub_item.get_state())

    def test_remove_initial_parent_with_apd_false_refcollection_sub_items(self):
        # LITPCDS-9406: Don't remove container item's sub items if APD=False
        self.manager.register_item_type(ItemType(
            "root",
            item=Child("item"),
            some_item=Child("some-item")
        ))
        self.manager.register_item_type(ItemType(
            "item",
            items=RefCollection("some-item")
        ))
        self.manager.register_item_type(ItemType("some-item"))

        self.manager.create_root_item("root")
        self.manager.create_item("item", "/item")
        self.manager.create_item("some-item", "/some_item")
        self.manager.create_inherited("/some_item", "/item/items/item1")
        self.manager.create_inherited("/some_item", "/item/items/item2")

        container = self.manager.get_item("/item")
        container._set_applied_properties_determinable(False)
        self.manager.remove_item("/item")
        self.assertEqual(ModelItem.ForRemoval, container.get_state())
        sub_item = self.manager.get_item("/item/items")
        self.assertEqual(ModelItem.ForRemoval, sub_item.get_state())
        sub_item = self.manager.get_item("/item/items/item1")
        self.assertEqual(ModelItem.ForRemoval, sub_item.get_state())
        sub_item = self.manager.get_item("/item/items/item2")
        self.assertEqual(ModelItem.ForRemoval, sub_item.get_state())

    def test_remove_initial_parent_with_apd_false_reference_sub_items(self):
        # LITPCDS-9406: Don't remove container item's sub items if APD=False
        self.manager.register_item_type(ItemType(
            "root",
            item=Child("item"),
            some_item=Child("some-item")
        ))
        self.manager.register_item_type(ItemType(
            "item",
            some_item=Reference("some-item")
        ))
        self.manager.register_item_type(ItemType("some-item"))

        self.manager.create_root_item("root")
        self.manager.create_item("item", "/item")
        self.manager.create_item("some-item", "/some_item")

        self.manager.create_inherited("/some_item",
            "/item/some_item")

        container = self.manager.get_item("/item")
        container._set_applied_properties_determinable(False)
        ref_source = self.manager.get_item("/some_item")
        self.manager.remove_item("/item")
        self.assertEqual(ModelItem.ForRemoval, container.get_state())
        sub_item = self.manager.get_item("/item/some_item")
        self.assertEqual(ModelItem.ForRemoval, sub_item.get_state())
        self.assertEqual(ModelItem.Initial, ref_source.get_state())

    def test_remove_initial_item_check_siblings_apd(self):
        # Test remove an item which has a sibling with APD=False. Item goes
        # to ForRemoval instead of being Removed directly.
        self._create_sibbling_structure()
        item = self.manager.get_item("/item/another_item")
        sibling_item = self.manager.get_item("/item/some_item")
        sibling_item._set_applied_properties_determinable(False)

        self.assertTrue(self.manager._has_siblings_or_their_descendants_apd_false(item))
        self.manager.remove_item(item.get_vpath())
        self.assertEqual(ModelItem.ForRemoval, item.get_state())

    def test_remove_initial_item_check_siblings_sub_items_apd(self):
        # Test remove an item which has siblings, with sub items
        # (grandchildren), one of which has an APD=False. Item goes to
        # ForRemoval instead of Removed directly.
        self._create_sibbling_structure()
        item = self.manager.get_item("/item/some_item")
        sibling_sub_item = self.manager.get_item("/item/another_item/yet_another_item")
        sibling_sub_item._set_applied_properties_determinable(False)

        self.assertTrue(self.manager._has_siblings_or_their_descendants_apd_false(item))
        self.manager.remove_item(item.get_vpath())
        self.assertEqual(ModelItem.ForRemoval, item.get_state())

    def test_remove_initial_container_check_siblings_apd(self):
        # Test removing an initial container item, which has sub items
        # (children), one of which has an APD=False. Siblings go to
        # ForRemoval instead of Removed directly
        self._create_sibbling_structure()
        container = self.manager.get_item("/item")
        child = self.manager.get_item("/item/some_item")
        child_sibling = self.manager.get_item("/item/another_item")

        child._set_applied_properties_determinable(False)
        self.manager.remove_item(container.get_vpath())
        self.assertEqual(ModelItem.ForRemoval, child.get_state())
        self.assertEqual(ModelItem.ForRemoval, child_sibling.get_state())
        self.assertEqual(ModelItem.ForRemoval, container.get_state())

    def test_remove_initial_container_check_siblings_sub_items_apd(self):
        # Test remove an initial container item, which has sub items with
        # sub items (grand children), one of which has an APD=False.
        # Siblings go to ForRemoval instead of Removed directly.
        self._create_sibbling_structure()
        container = self.manager.get_item("/item")
        item = self.manager.get_item("/item/some_item")
        sibling = self.manager.get_item("/item/another_item")
        sibling_sub_item = self.manager.get_item("/item/another_item/yet_another_item")
        sibling_sub_item._set_applied_properties_determinable(False)
        self.manager.remove_item(container.get_vpath())

        self.assertEqual(ModelItem.ForRemoval, item.get_state())
        self.assertEqual(ModelItem.ForRemoval, sibling.get_state())
        self.assertEqual(ModelItem.ForRemoval, container.get_state())

    def test_set_applied_properties_determinable(self):
        def _reset_item_and_all_tasks(node, tasks):
            node._set_applied_properties_determinable(True)
            for task in tasks:
                task.state = constants.TASK_SUCCESS
                task.lock_type = 'type_other'
                task.is_snapshot_task = False

        self._create_deployment_and_a_couple_of_nodes()
        node = self.manager.query_by_vpath("/deployments/d1/nodes/node1")
        mock_task1 = MockTask()
        mock_task2 = MockTask()
        mock_task3 = MockTask()
        task_list = [mock_task1, mock_task2, mock_task3]
        item_tasks = {node.vpath: task_list}
        # Test for indeterminable properties
        # All tasks initial, failed plan, APD=True
        self.manager._set_applied_properties_determinable(item_tasks)
        self.assertEquals(True, node.applied_properties_determinable)
        # All tasks successfull, item APD=True, failed plan
        _reset_item_and_all_tasks(node, task_list)
        self.manager._set_applied_properties_determinable(item_tasks)
        self.assertEquals(True, node.applied_properties_determinable)
        # One task not successfull, APD=False
        _reset_item_and_all_tasks(node, task_list)
        mock_task3.state = constants.TASK_STOPPED
        self.manager._set_applied_properties_determinable(item_tasks)
        self.assertEquals(False, node.applied_properties_determinable)
        # Failed lock tasks, APD doesn't go to False
        _reset_item_and_all_tasks(node, task_list)
        mock_task1.lock_type = Task.TYPE_LOCK
        mock_task1.state = constants.TASK_FAILED
        mock_task3.lock_type = Task.TYPE_UNLOCK
        mock_task3.state = constants.TASK_STOPPED
        self.manager._set_applied_properties_determinable(item_tasks)
        self.assertEquals(True, node.applied_properties_determinable)

        # All tasks are initial, APD=False
        for task in task_list:
            task.state = constants.TASK_INITIAL

        node._set_applied_properties_determinable(False)
        self.manager._set_applied_properties_determinable(item_tasks)
        self.assertEquals(False, node.applied_properties_determinable)

        # All tasks are initial, APD=True
        node._set_applied_properties_determinable(True)
        self.assertEquals(True, node.applied_properties_determinable)

        # Applied item with APD=False, successful plan -> APD=True
        _reset_item_and_all_tasks(node, task_list)
        node._set_applied_properties_determinable(False)
        self.manager._set_applied_properties_determinable(item_tasks)
        self.assertEquals(True, node.applied_properties_determinable)

    def test_set_applied_properties_determinable_failed_deconfigure(self):
        self.manager.register_item_type(ItemType("root",
            grandparents=Collection("grandparent"),
        ))

        self.manager.register_item_type(ItemType("grandparent",
            parents=Collection("parent"),
        ))

        self.manager.register_item_type(ItemType("parent",
            grandchildren=Collection("grandchild"),
        ))

        self.manager.register_item_type(ItemType("grandchild",
            hostname=Property("basic_string", required=True),
        ))

        self.manager.create_core_root_items()
        self.manager.create_item("grandparent", "/grandparents/gp")
        self.manager.create_item("parent", "/grandparents/gp/parents/p")
        self.manager.create_item("grandchild", "/grandparents/gp/parents/p/grandchildren/gc", hostname="foo")
        self.manager.create_item("grandchild", "/grandparents/gp/parents/p/grandchildren/other_gc", hostname="bar")

        grandparent = self.manager.query_by_vpath("/grandparents/gp")

        grandparent.set_for_removal()
        grandparent._previous_state = ModelItem.Applied

        grandparent.parents.p.set_for_removal()
        grandparent.parents.p._previous_state = ModelItem.Applied

        grandparent.parents.p.grandchildren.gc.set_for_removal()
        grandparent.parents.p.grandchildren.gc._previous_state = ModelItem.Applied
        grandparent.parents.p.grandchildren.other_gc.set_for_removal()
        grandparent.parents.p.grandchildren.other_gc._previous_state = ModelItem.Applied

        grandparent_deconfigure = MockTask()
        parent_deconfigure = MockTask()
        grandchild_deconfigure = MockTask()
        other_grandchild_deconfigure = MockTask()

        item_tasks = {
            grandparent.vpath: [grandparent_deconfigure],
            grandparent.parents.p.vpath: [parent_deconfigure],
            grandparent.parents.p.grandchildren.gc.vpath: [grandchild_deconfigure],
            grandparent.parents.p.grandchildren.other_gc.vpath: [other_grandchild_deconfigure],
        }

        # Test for indeterminable properties
        grandparent_deconfigure.state = constants.TASK_SUCCESS
        grandparent_deconfigure.lock_type = 'type_other'

        parent_deconfigure.state = constants.TASK_SUCCESS
        parent_deconfigure.lock_type = 'type_other'

        grandchild_deconfigure.state = constants.TASK_INITIAL
        grandchild_deconfigure.lock_type = 'type_other'

        other_grandchild_deconfigure.state = constants.TASK_SUCCESS
        other_grandchild_deconfigure.lock_type = 'type_other'

        grandparent.set_removed()
        grandparent.parents.p.set_removed()
        grandparent.parents.p.grandchildren.other_gc.set_removed()

        self.manager.delete_removed_items_after_plan()
        self.manager._set_applied_properties_determinable(item_tasks)

        self.assertTrue(grandparent.is_for_removal())
        self.assertTrue(grandparent.parents.p.is_for_removal())
        self.assertTrue(grandparent.parents.p.grandchildren.gc.is_for_removal())

        # The wget reference under node1/packages entered the Removed state and
        # was successfully deleted from the model, since doing so doesn't
        # compromise model integrity unlike deleting the Removed parent of
        # ForRemoval items
        self.assertRaises(
            ModelManagerException,
            self.manager.query_by_vpath,
            "/grandparents/gp/parents/p/grandchildren/other_gc"
        )

        # The grandparent item has had a successful deconfigure task, but is is
        # back in the FR state. We need its APD flag to be false so that the
        # deconfigure task is not filtered out in the next plan
        self.assertEquals(False, grandparent.applied_properties_determinable)

        # The parent item has had a successful deconfigure task, but is is
        # back in the FR state. We need its APD flag to be false so that the
        # deconfigure task is not filtered out in the next plan
        self.assertEquals(False, grandparent.parents.p.applied_properties_determinable)

        # The grandchild item has a deconfigure task that has not run - it
        # never entered the Removed state and its APD flag should be True.
        self.assertEquals(True, grandparent.parents.p.grandchildren.gc.applied_properties_determinable)

    def test_delete_structure(self):
        self.manager.register_item_type(ItemType(
            "root",
            item=Child("item"),
        ))
        self.manager.register_item_type(ItemType(
            "item",
            items=Collection("item")
        ))
        self.manager.create_root_item("root")
        self.manager.create_item("item", "/item")
        self.manager.create_item("item", "/item/items/item1")
        self.manager.create_item("item", "/item/items/item1/items/item11")
        self.manager.create_item("item", "/item/items/item1/items/item12")
        self.manager.create_item("item", "/item/items/item2")
        self.manager.create_item("item", "/item/items/item2/items/item21")
        self.manager.create_item("item", "/item/items/item2/items/item22")

        self.manager.get_item("/item/items/item1/items/item11").set_applied()

        self.manager.remove_item("/item")

        item = self.manager.get_item("/item")
        self.assertTrue(item is not None)
        self.assertEquals(ModelItem.ForRemoval, item.get_state())

        item = self.manager.get_item("/item/items")
        self.assertTrue(item is not None)
        self.assertEquals(ModelItem.ForRemoval, item.get_state())

        item = self.manager.get_item("/item/items/item1")
        self.assertTrue(item is not None)
        self.assertEquals(ModelItem.ForRemoval, item.get_state())

        item = self.manager.get_item("/item/items/item1/items/item11")
        self.assertTrue(item is not None)
        self.assertEquals(ModelItem.ForRemoval, item.get_state())

        item = self.manager.get_item("/item/items/item1/items/item12")
        self.assertTrue(item is None)

        item = self.manager.get_item("/item/items/item2")
        self.assertTrue(item is None)

        item = self.manager.get_item("/item/items/item2/items")
        self.assertTrue(item is None)

        item = self.manager.get_item("/item/items/item2/items21")
        self.assertTrue(item is None)

        item = self.manager.get_item("/item/items/item2/items22")
        self.assertTrue(item is None)

    def test_delete_collection(self):
        self.manager.register_item_type(ItemType(
            "root",
            items=Collection("item"),
            ref_items=RefCollection("item"),
        ))
        self.manager.register_item_type(ItemType(
            "item",
            name=Property("basic_string"),
        ))
        self.manager.create_root_item("root")

        ret = self.manager.remove_item("/items")
        self.assertEquals(1, len(ret))
        error = ret[0]
        self.assertTrue(isinstance(error, ValidationError))
        self.assertEquals(constants.METHOD_NOT_ALLOWED_ERROR, error.error_type)
        self.assertEquals("/items", error.item_path)

        ret = self.manager.remove_item("/ref_items")
        self.assertEquals(1, len(ret))
        error = ret[0]
        self.assertTrue(isinstance(error, ValidationError))
        self.assertEquals(constants.METHOD_NOT_ALLOWED_ERROR, error.error_type)
        self.assertEquals("/ref_items", error.item_path)

    def test_register_property_type_twice(self):
        self.assertRaises(Exception, self.manager.register_property_type,
            PropertyType("basic_string"),
        )

    def test_register_item_type_twice(self):
        self.manager.register_item_type(ItemType(
            "item",
            name=Property("basic_string"),
        ))
        self.assertRaises(Exception, self.manager.register_item_type, ItemType(
            "item",
            name=Property("basic_string"),
        ))

    def test_query_queryitem(self):
        self.manager.register_item_type(ItemType("root",
            software=Child("software", required=True),
            deployments=Child("deployments", required=True, require="ms"),
        ))
        self.manager.register_item_type(ItemType("deployments",
            nodes=Collection("node"),
        ))
        self.manager.register_item_type(ItemType("node",
            hostname=Property("basic_string", required=True),
            packages=RefCollection("package"),
        ))
        self.manager.register_item_type(ItemType("software",
            items=Collection("package"),
        ))
        self.manager.register_item_type(ItemType("package",
            name=Property("basic_string"),
        ))

        root = self.manager.create_root_item("root")
        vim = self.manager.create_item("package", "/software/items/vim",
            name="vim")
        self.manager.create_item("node", "/deployments/nodes/node1",
            hostname="node1")
        self.manager.create_inherited("/software/items/vim",
            "/deployments/nodes/node1/packages/vim")
        self.manager.create_item("node", "/deployments/nodes/node2",
            hostname="node2")
        self.manager.create_inherited("/software/items/vim",
            "/deployments/nodes/node2/packages/vim")

        node = QueryItem(self.manager,
                self.manager.query("node")[0])
        self.assertEquals(1, len(node.query("package")))
        self.assertEquals(1, len(self.manager.query("package")))

    def _setUp_views(self):
        self.manager.register_item_type(ItemType("root",
            profiles=Collection("mock_np"),
            nodes=Collection("node"),
            systems=Collection("system"),
        ))

        self.manager.register_item_type(ItemType("node",
            hostname=Property("basic_string"),
            system=Reference("system"),
            np=Reference("mock_np"),
        ))

        self.manager.register_item_type(ItemType("system",
            name=Property("basic_string"),
            nic=Child("nic"),
        ))

        self.manager.register_item_type(ItemType("nic",
            name=Property("basic_string"),
            mac=Property("basic_string"),
        ))

        self.manager.register_item_type(ItemType("mock_np",
            networks=Collection("mock_network"),
            interfaces=Collection("mock_interface"),
            bridges=Collection("mock_bridge"),
            name=Property("basic_string")
        ))

        self.get_plugin_api_from_view = mock.Mock()
        self.manager.register_item_type(ItemType("mock_network",
            interface=Property("basic_string"),
            bridge=Property("basic_string"),
            foo=View('basic_string', self.dummy_API_method),
            bar=View('basic_string', self.exception_API_method),
            baz=View('basic_string', self.viewerror_API_method),
            access=View('basic_string', self.qi_access_method),
            type=View('basic_string', self.qi_type_method),
            parent_node=View('basic_string', self.parent_lookup_method),
            plugin_api=View('basic_string', self.get_plugin_api_from_view),
            modified_model=View('basic_string', self.modify_model_from_view)
       ))

        self.manager.register_item_type(ItemType("mock_interface",
            name=Property("basic_string"),
        ))

        self.manager.register_item_type(ItemType("mock_bridge",
            name=Property("basic_string"),
        ))

        root = self.manager.create_root_item("root")
        self.manager.create_item("system", "/systems/system_A",
                                         hostname="alice")
        self.manager.create_item("nic", "/systems/system_A/nic",
                name="eth0", mac="12:34")

        self.manager.create_item("system", "/systems/system_B",
                                         hostname="bob")
        self.manager.create_item("nic", "/systems/system_B/nic",
                name="eth99", mac="56:78")

        self.node1 = self.manager.create_item("node", "/nodes/node1",
                hostname="test1")
        self.node2 = self.manager.create_item("node", "/nodes/node2",
                hostname="test2")

        # fgfd
        self.manager.create_item("mock_np", "/profiles/profile_A",
                name="alpha")
        self.manager.create_item("mock_network",
                "/profiles/profile_A/networks/net1", interface="if1")
        self.manager.create_item("mock_interface",
                "/profiles/profile_A/interfaces/if1", name="eth0")

        self.manager.create_item("mock_np", "/profiles/profile_B",
                name="beta")

        self.manager.create_inherited("/profiles/profile_A",
                                      "/nodes/node1/np")

    @staticmethod
    def dummy_API_method(plugin_api_context, query_item):
        return 123456

    @staticmethod
    def exception_API_method(plugin_api_context, query_item):
        return 6 / 0

    @staticmethod
    def viewerror_API_method(plugin_api_context, query_item):
        raise ViewError("Oh no")

    @staticmethod
    def qi_access_method(plugin_api_context, query_item):
        return query_item.get_vpath()

    @staticmethod
    def qi_type_method(plugin_api_context, query_item):
        return str(type(query_item))

    @staticmethod
    def parent_lookup_method(plugin_api_context, query_item):
        # We could use the query item's model item and grab its parent, but
        # that would be cheating. We'll have to do a separate lookup instead
        for node in plugin_api_context.query('node'):
            if not node.np:
                continue
            if not node.np.networks:
                continue
            if node.np.networks.net1 == query_item:
                return node
        raise ViewError("parent node not found")

    @staticmethod
    def modify_model_from_view(plugin_api_context, query_item):
        plugin_api_context.update_item('/nodes/')

    def test_view_value(self):
        self._setUp_views()
        node1_qi = QueryItem(self.manager,
                self.manager.query("node", hostname="test1")[0])
        self.assertEquals(123456, node1_qi.np.networks.net1.foo)

    def test_exception_cuaght_as_viewerror(self):
        self._setUp_views()
        node1_qi = QueryItem(self.manager,
                self.manager.query("node", hostname="test1")[0])
        self.assertRaises(ViewError, getattr, node1_qi.np.networks.net1, 'bar')

    def test_viewerror_thrown(self):
        self._setUp_views()
        node1_qi = QueryItem(self.manager,
                    self.manager.query("node", hostname="test1")[0])
        self.assertRaises(ViewError, getattr, node1_qi.np.networks.net1, 'baz')

    def test_access(self):
        self._setUp_views()
        node1_qi = QueryItem(self.manager,
                self.manager.query("node", hostname="test1")[0])
        self.assertEquals('/nodes/node1/np/networks/net1',
                node1_qi.np.networks.net1.access)

    def test_type(self):
        self._setUp_views()
        node1_qi = QueryItem(self.manager,
                self.manager.query("node", hostname="test1")[0])
        self.assertEquals("<class 'litp.core.model_manager.QueryItem'>",
                node1_qi.np.networks.net1.type)

    def test_parent_lookup(self):
        self._setUp_views()
        node1_qi = QueryItem(self.manager,
                self.manager.query("node", hostname="test1")[0])
        self.assertEquals(node1_qi, node1_qi.np.networks.net1.parent_node)

    def test_parent_lookup_failure(self):
        self._setUp_views()
        unlinked_network = self.manager.create_item("mock_network",
                "/profiles/profile_B/networks/net_foo", interface="foo")
        unlinked_network_qi = QueryItem(self.manager,
                self.manager.query("mock_network", interface="foo")[0])
        self.assertRaises(ViewError, getattr, unlinked_network_qi, 'parent_node')

    def test_view_callable_method_receives_plugin_api_context(self):
        self._setUp_views()
        view_vpath = '/profiles/profile_A/networks/net1'
        view_parent = QueryItem(self.manager,
                self.manager.query_by_vpath(view_vpath))
        getattr(view_parent, 'plugin_api')
        self.assertEqual(type(self.get_plugin_api_from_view.call_args[0][0]),
                         PluginApiContext)

    def test_view_cannot_modify_model(self):
        self._setUp_views()
        view_vpath = '/profiles/profile_A/networks/net1'
        view_parent = QueryItem(self.manager,
                self.manager.query_by_vpath(view_vpath))
        self.assertRaises(ViewError, getattr, view_parent, 'modified_model')

    def test__get_readonly_properties(self):
        self.manager.register_item_type(ItemType("root",
            nodes=Collection("node"),
            systems=Collection("system"),
        ))
        self.manager.register_item_type(ItemType("node",
            hostname=Property("basic_string"),
            system=Reference("system"),
        ))

        property_name = Property("basic_string", updatable_rest=False)
        property_other = Property("basic_string", updatable_rest=False)
        property_yet_another = Property("basic_string")

        self.manager.register_item_type(ItemType("system",
            name=property_name, other=property_other,
            yet_another=property_yet_another,
            foo=View('basic_string', self.dummy_API_method)))
        self.manager.create_root_item("root")

        sys1 = self.manager.create_item("system", "/systems/system1",
            name="mistersystem", other="foo", yet_another="bar")

        expected_props = {'other': 'foo',
                'name': 'mistersystem'}

        ro_props = self.manager._get_readonly_properties(sys1,
                sys1._properties)

        self.assertEquals(expected_props, ro_props)

    def test_update_readonly_properties_succes(self):
        self.manager.register_item_type(ItemType("root",
            nodes=Collection("node"),
            systems=Collection("system"),
        ))
        self.manager.register_item_type(ItemType("node",
            hostname=Property("basic_string"),
            system=Reference("system"),
        ))

        property_name = Property("basic_string", updatable_rest=False)
        property_other = Property("basic_string", updatable_rest=False)
        property_optional = Property("basic_string", updatable_rest=False, required=False)
        property_yet_another = Property("basic_string")

        self.manager.register_item_type(ItemType("system",
            name=property_name, other=property_other,
            optional=property_optional,
            yet_another=property_yet_another))
        self.manager.create_root_item("root")

        sys1 = self.manager.create_item("system", "/systems/system1",
            name="mistersystem", other="foo", yet_another="bar")
        sys1 = self.manager.get_item(sys1.vpath)
        self.assertEquals(ModelItem.Initial, sys1.get_state())

        sys1 = self.manager.update_item("/systems/system1", name="xx")
        self.assertTrue(isinstance(sys1, ModelItem))
        self.assertEquals("xx", sys1.name)

        self.manager.set_all_applied()
        sys1 = self.manager.get_item(sys1.vpath)
        self.assertEquals('Applied', sys1.get_state())

        updated_item = self.manager.update_item('/systems/system1',
                yet_another='ccc')

        sys1 = self.manager.get_item(sys1.vpath)
        self.assertEquals('Updated', sys1.get_state())
        self.assertEquals(sys1, updated_item)
        sys1.set_applied()

        self.assertEquals('Applied', sys1.get_state())
        updated_item = self.manager.update_item('/systems/system1', optional='foo')
        self.assertTrue(sys1.is_updated())
        self.assertEquals(sys1, updated_item)

        updated_item = self.manager.update_item('/systems/system1', optional='bar')
        self.assertTrue(sys1.is_updated())
        self.assertEquals(sys1, updated_item)

        sys1.set_applied()
        updated_item = self.manager.update_item('/systems/system1', optional='bar')
        self.assertTrue(sys1.is_applied())
        self.assertEquals(sys1, updated_item)

    def test_update_readonly_properties_fail(self):
        self.manager.register_item_type(ItemType("root",
            nodes=Collection("node"),
            systems=Collection("system"),
        ))
        self.manager.register_item_type(ItemType("node",
            hostname=Property("basic_string"),
            system=Reference("system"),
        ))

        property_name = Property("basic_string", updatable_rest=False)
        property_other = Property("basic_string", updatable_rest=False)
        property_optional = Property("basic_string", updatable_rest=False, required=False)
        property_yet_another = Property("basic_string")

        self.manager.register_item_type(ItemType("system",
            name=property_name, other=property_other,
            yet_another=property_yet_another,
            optional=property_optional,
            foo=View('basic_string', self.dummy_API_method)))
        self.manager.create_root_item("root")

        sys1 = self.manager.create_item("system", "/systems/system1",
            name="mistersystem", other="foo", yet_another="bar")

        self.manager.set_all_applied()
        sys1 = self.manager.get_item(sys1.vpath)
        self.assertEquals('Applied', sys1.get_state())

        errors = self.manager.update_item('/systems/system1',
                name='aaa', other='bbb', yet_another='ccc', foo='bar')

        sys1 = self.manager.get_item(sys1.vpath)
        self.assertEquals('Applied', sys1.get_state())
        self.assertEquals(errors[0].error_type, constants.INVALID_REQUEST_ERROR)
        self.assertEquals(errors[1].error_type, constants.INVALID_REQUEST_ERROR)
        self.assertEquals(3, len(errors))
        self.assertEquals('other', errors[0].property_name)
        self.assertEquals('Unable to modify readonly property: other',
                errors[0].error_message)
        self.assertEquals('name', errors[1].property_name)
        self.assertEquals('Unable to modify readonly property: name',
                errors[1].error_message)
        self.assertEquals('foo', errors[2].property_name)
        self.assertEquals('"foo" is a read-only view of system',
                errors[2].error_message)


        sys1 = self.manager.get_item(sys1.vpath)
        self.assertEquals('Applied', sys1.get_state())
        self.assertFalse('optional' in sys1.get_applied_properties())
        updated_item = self.manager.update_item('/systems/system1', optional='foo')
        self.assertTrue(sys1.is_updated())
        self.assertEquals(sys1, updated_item)
        self.assertFalse('optional' in sys1.get_applied_properties())

        updated_item = self.manager.update_item('/systems/system1', optional='bar')
        self.assertTrue(sys1.is_updated())
        self.assertEquals(sys1, updated_item)
        self.assertFalse('optional' in sys1.get_applied_properties())
        sys1.set_applied()

        self.assertTrue('optional' in sys1.get_applied_properties())
        errors = self.manager.update_item('/systems/system1', optional='new_value')
        self.assertEquals(1, len(errors))
        self.assertEquals('optional', errors[0].property_name)
        self.assertEquals('Unable to modify readonly property: optional',
                errors[0].error_message)
        self.assertTrue(sys1.is_applied())

    def test_update_readonly_reverts_state(self):
        self.manager.register_item_type(ItemType("root",
            systems=Collection("system"),
        ))

        self.manager.register_item_type(ItemType("system",
            name=Property("basic_string", updatable_rest=False),
            other=Property("basic_string", updatable_rest=False),
            yet_another=Property("basic_string"),
            foo=View('basic_string', self.dummy_API_method)))

        self.manager.create_root_item("root")

        sys1 = self.manager.create_item("system", "/systems/system1",
            name="mistersystem", other="foo", yet_another="bar")

        self.manager.set_all_applied()
        sys1 = self.manager.get_item(sys1.vpath)
        self.assertTrue(sys1.is_applied())

        sys1 = self.manager.remove_item(sys1.vpath)
        self.assertTrue(sys1.is_for_removal())
        errors = self.manager.update_item('/systems/system1',
                name='aaa', other='bbb', yet_another='ccc', foo='bar')

        sys1 = self.manager.get_item(sys1.vpath)
        self.assertTrue(sys1.is_for_removal())
        self.assertEquals(errors[0].error_type, constants.INVALID_REQUEST_ERROR)
        self.assertEquals(errors[1].error_type, constants.INVALID_REQUEST_ERROR)
        self.assertEquals(3, len(errors))
        self.assertEquals('other', errors[0].property_name)
        self.assertEquals('Unable to modify readonly property: other',
                errors[0].error_message)
        self.assertEquals('name', errors[1].property_name)
        self.assertEquals('Unable to modify readonly property: name',
                errors[1].error_message)
        self.assertEquals('foo', errors[2].property_name)
        self.assertEquals('"foo" is a read-only view of system',
                errors[2].error_message)


    def test__get_updatable_plugin_properties(self):
        property_name = Property("basic_string",
                updatable_plugin=True, updatable_rest=False)
        property_other = Property("basic_string",
                updatable_plugin=True, updatable_rest=False)
        property_yet_another = Property("basic_string")

        item_type = ItemType("system",
            name=property_name,
            other=property_other,
            yet_another=property_yet_another)

        errors = self.manager._get_updatable_plugin_properties(
                item_type,
                {'name': 'XYZ', 'other': 'ABC', 'yet_another': 'DEF'})

        expected_properties = {'other': 'ABC', 'name': 'XYZ'}
        self.assertEquals(expected_properties, errors)

    def test_update_ignore_views_litpcds_4915(self):
        self.manager.register_item_type(ItemType("root",
            nodes=Collection("node"),
            systems=Collection("system"),
        ))
        self.manager.register_item_type(ItemType("node",
            hostname=Property("basic_string"),
            system=Reference("system"),
        ))
        self.manager.register_item_type(ItemType("system",
            name=Property("basic_string"),
            foo=View('basic_string', self.dummy_API_method),
        ))
        self.manager.create_root_item("root")
        systemA = self.manager.create_item(
            "system", "/systems/system_A", name="systemA")
        self.node1 = self.manager.create_item(
            "node", "/nodes/node1", hostname="test1")
        systemA_ref = self.manager.create_inherited(
            "/systems/system_A", "/nodes/node1/system")

        self.manager.set_all_applied()

        # In LITPCDS-4915 there is no View in item.properties
        # del systemA_ref._properties['foo']
        systemA_ref = self.manager.get_item(systemA_ref.vpath)

        self.assertEquals("Applied", systemA_ref.get_state())
        systemA_ref = self.manager.remove_item(systemA_ref.vpath)
        self.assertEquals("ForRemoval", systemA_ref.get_state())
        systemA_ref = self.manager.create_inherited(
            "/systems/system_A", "/nodes/node1/system")
        self.assertEquals("Applied", systemA_ref.get_state())

    def test_handle_upgrade_item_bad_path(self):
        self._create_deployment_and_a_couple_of_nodes()
        self.assertRaises(ModelManagerException,
                          self.manager.handle_upgrade_item,
                          '/bad/path',
                          'id')

    def test_handle_upgrade_item_bad_item(self):
        # only nodes, clusters or deployments are accepted
        self._create_deployment_and_a_couple_of_nodes()
        self.assertNotEqual(None,
            self.manager.handle_upgrade_item('/deployments/d1/nodes/node1/os',
                                             'id'))

    def test_handle_upgrade_item_node_level(self):
        self._create_deployment_and_a_couple_of_nodes()
        self.assertEqual(None,
                self.manager.handle_upgrade_item("/deployments/d1/nodes/node1",
                                                 'id'))
        self.assertNotEqual(None,
                self.manager.get_item("/deployments/d1/nodes/node1/upgrade"))
        self.assertEqual(None,
                self.manager.get_item("/deployments/d1/nodes/node2/upgrade"))

    def test_handle_upgrade_item_deployment_level(self):
        self._create_deployment_and_a_couple_of_nodes()
        self.assertEqual(None,
                self.manager.handle_upgrade_item("/deployments/d1", 'id'))
        self.assertNotEqual(None,
                self.manager.get_item("/deployments/d1/nodes/node1/upgrade"))
        self.assertNotEqual(None,
                self.manager.get_item("/deployments/d1/nodes/node2/upgrade"))

    def test_upgrade_hash_changes(self):
        self._create_deployment_and_a_couple_of_nodes()
        self.assertEqual(None,
                self.manager.handle_upgrade_item("/deployments/d1/nodes/node1",
                                                 'id'))
        self.assertEqual("id",
            self.manager.get_item("/deployments/d1/nodes/node1/upgrade").hash)
        self.assertEqual(None,
                self.manager.handle_upgrade_item("/deployments/d1", 'another_id'))
        self.assertEqual("another_id",
            self.manager.get_item("/deployments/d1/nodes/node1/upgrade").hash)
        self.assertEqual("another_id",
            self.manager.get_item("/deployments/d1/nodes/node2/upgrade").hash)
        self.assertEqual('Initial', self.manager.get_item("/deployments/d1/nodes/node1/upgrade").get_state())

    def test_upgrade_hash_changes_applied_state(self):
        self._create_deployment_and_a_couple_of_nodes()
        self.assertEqual(None,
                self.manager.handle_upgrade_item("/deployments/d1/nodes/node1",
                                                 'id'))
        n1_up = self.manager.get_item("/deployments/d1/nodes/node1/upgrade")
        n1_up.set_applied()

        # Update upgrade item
        self.assertEqual(None,
                self.manager.handle_upgrade_item("/deployments/d1", 'another_id'))
        self.assertEqual(ModelItem.Updated, n1_up.get_state())

    def test_upgrade_hash_changes_for_removal_state(self):
        self._create_deployment_and_a_couple_of_nodes()
        self.assertEqual(None,
                self.manager.handle_upgrade_item("/deployments/d1/nodes/node1",
                                                 'id'))
        n1_up = self.manager.get_item("/deployments/d1/nodes/node1/upgrade")
        n1_up.set_for_removal()

        self.assertEqual(None,
                self.manager.handle_upgrade_item("/deployments/d1", 'another_id'))
        self.assertEqual(ModelItem.Updated, n1_up.get_state())

    def test_handle_upgrade_item_node_for_removal(self):
        self._create_deployment_and_a_couple_of_nodes()
        node1_mi = self.manager.get_item("/deployments/d1/nodes/node1")
        node2_mi = self.manager.get_item("/deployments/d1/nodes/node2")
        node2_mi.set_for_removal()

        with mock.patch.object(self.manager, '_process_upgradeitem_in_node') as mock_process:
            # We don't have a result to return when we skip the node in ForRemoval
            self.assertEqual(
                None,
                self.manager.handle_upgrade_item("/deployments/d1/nodes/node2", 'id')
            )
            self.assertEqual([], mock_process.mock_calls)

            # We don't have a result to return when we process the node that's Applied
            self.assertEqual(
                None,
                self.manager.handle_upgrade_item("/deployments/d1/nodes/node1", 'id')
            )
            # ...but we do call _process_upgradeitem_in_node
            mock_process.assert_called_with(node1_mi, "id")

    def test_requires_reboot_is_deleted(self):
        self._create_deployment_and_a_couple_of_nodes()
        self.manager.create_item('upgrade', '/deployments/d1/nodes/node1/upgrade',
                                hash='hash',
                                requires_reboot='false')
        # simulate a successful plan
        self.manager.query('upgrade')[0].set_applied()
        self.assertEqual('false', self.manager.query('upgrade')[0].requires_reboot)
        self.manager.handle_upgrade_item("/deployments/d1/nodes/node1", 'another_id')
        self.assertEqual(None, self.manager.query('upgrade')[0].requires_reboot)
        self.assertEqual('Updated', self.manager.query('upgrade')[0].get_state())

    def test_reboot_performed_is_deleted(self):
        self._create_deployment_and_a_couple_of_nodes()
        self.manager.create_item('upgrade', '/deployments/d1/nodes/node1/upgrade',
                                hash='hash',
                                reboot_performed='false')
        # simulate a successful plan
        self.manager.query('upgrade')[0].set_applied()
        self.assertEqual('false', self.manager.query('upgrade')[0].reboot_performed)
        self.manager.handle_upgrade_item("/deployments/d1/nodes/node1", 'another_id')
        self.assertEqual(None, self.manager.query('upgrade')[0].reboot_performed)

    def test_upgrade_props_notset_is_deleted(self):
        self._create_deployment_and_a_couple_of_nodes()
        self.manager.create_item('upgrade', '/deployments/d1/nodes/node1/upgrade',
                                hash='hash',
                                reboot_performed='false')
        self.manager.handle_upgrade_item("/deployments/d1/nodes/node1", 'another_id')
        self.assertEqual(None, self.manager.query('upgrade')[0].disable_reboot)
        self.assertEqual(None, self.manager.query('upgrade')[0].ha_manager_only)
        self.assertEqual(None, self.manager.query('upgrade')[0].os_reinstall)
        self.assertEqual(None, self.manager.query('upgrade')[0].redeploy_ms)
        self.assertEqual(None, self.manager.query('upgrade')[0].pre_os_reinstall)
        self.assertEqual(None, self.manager.query('upgrade')[0].infra_update)

    def test_upgrade_props_set_is_deleted(self):
        self._create_deployment_and_a_couple_of_nodes()
        self.manager.create_item('upgrade', '/deployments/d1/nodes/node1/upgrade',
                                hash='hash',
                                disable_reboot='true',
                                ha_manager_only='true',
                                os_reinstall='true',
                                redeploy_ms='true',
                                pre_os_reinstall='true',
                                infra_update='true')
        # simulate a successful plan
        self.assertEqual('true', self.manager.query('upgrade')[0].disable_reboot)
        self.assertEqual('true', self.manager.query('upgrade')[0].ha_manager_only)
        self.assertEqual('true', self.manager.query('upgrade')[0].os_reinstall)
        self.assertEqual('true', self.manager.query('upgrade')[0].redeploy_ms)
        self.assertEqual('true', self.manager.query('upgrade')[0].pre_os_reinstall)
        self.assertEqual('true', self.manager.query('upgrade')[0].infra_update)

        self.manager.handle_upgrade_item("/deployments/d1/nodes/node1", 'another_id')
        self.assertEqual(None, self.manager.query('upgrade')[0].disable_reboot)
        self.assertEqual(None, self.manager.query('upgrade')[0].ha_manager_only)
        self.assertEqual(None, self.manager.query('upgrade')[0].os_reinstall)
        self.assertEqual(None, self.manager.query('upgrade')[0].redeploy_ms)
        self.assertEqual(None, self.manager.query('upgrade')[0].pre_os_reinstall)
        self.assertEqual(None, self.manager.query('upgrade')[0].infra_update)

    def test_snapshot_item_is_deleted(self):
        self._create_deployment_and_a_couple_of_nodes()
        self.manager.create_item("snapshot-base", "/snapshots/snapshot", timestamp=None)
        self.assertTrue(self.manager.get_item("/snapshots/snapshot").is_initial())
        self.manager.remove_snapshot_item('snapshot')
        self.assertTrue(not self.manager.get_item("/snapshots/snapshot"))
        # now with for_removal
        self.manager.create_item("snapshot-base", "/snapshots/snapshot", timestamp=None)
        self.manager.get_item("/snapshots/snapshot").set_for_removal()
        self.assertTrue(self.manager.get_item("/snapshots/snapshot").is_for_removal())
        self.manager.remove_snapshot_item('snapshot')
        self.assertTrue(not self.manager.get_item("/snapshots/snapshot"))
        # now with removed
        self.manager.create_item("snapshot-base", "/snapshots/snapshot", timestamp=None)
        self.manager.get_item("/snapshots/snapshot").set_removed()
        self.assertTrue(self.manager.get_item("/snapshots/snapshot").is_removed())
        self.manager.remove_snapshot_item('snapshot')
        self.assertTrue(not self.manager.get_item("/snapshots/snapshot"))

    def _create_deployment_and_a_couple_of_nodes(self, nodes=['node1', 'node2']):
        self.manager.register_item_type(ItemType("root",
            software=Child("software", required=True),
            deployments=Collection("deployment"),
            ms=Child("node", required=True),
            snapshots=Collection("snapshot-base", max_count=1),
        ))
        self.manager.register_item_type(ItemType("deployment",
            nodes=Collection("node"),
        ))
        self.manager.register_item_type(ItemType("node",
            hostname=Property("basic_string", required=True),
            os=Reference("os-profile"),
            packages=RefCollection("package"),
            upgrade=Child("upgrade"),
            custom_name=Property("basic_string"),
        ))
        self.manager.register_item_type(ItemType("software",
            profiles=Collection("os-profile"),
            items=Collection("package"),
        ))
        self.manager.register_item_type(ItemType("os-profile",
            name=Property("basic_string"),
        ))
        self.manager.register_item_type(ItemType("package",
            name=Property("basic_string"),
        ))
        self.manager.register_item_type(ItemType("upgrade",
                hash=Property(
                    "basic_string",
                    prop_description="Upgrade id.",
                    required=True,
                    updatable_plugin=True,
                    ),
                requires_reboot=Property(
                    "basic_string",
                    prop_description="Whether the upgrade requires a "
                    "node reboot.",
                    required=False,
                    updatable_plugin=True,
                    updatable_rest=False
                ),
                reboot_performed=Property(
                    "basic_string",
                    prop_description="Whether the node rebooted.",
                    required=False,
                    updatable_plugin=True,
                    updatable_rest=False
                ),
                disable_reboot=Property(
                    "basic_boolean",
                    prop_description="Disable the LITP generated reboot.",
                    required=False,
                    configuration=False
                ),
                os_reinstall=Property(
                    "basic_boolean",
                    prop_description="OS re-install.",
                    required=False,
                    configuration=False
                ),
                ha_manager_only=Property(
                    "basic_boolean",
                    prop_description="Confine task generation to upgrade" +
                     " the HA Manager only.",
                    required=False,
                    configuration=False
                ),
                redeploy_ms=Property(
                    "basic_boolean",
                    prop_description="Redeploy MS.",
                    required=False,
                    configuration=False
                ),
                infra_update=Property(
                    "basic_boolean",
                    prop_description="Infrastructure update.",
                    required=False,
                    configuration=False
                ),
                pre_os_reinstall=Property(
                    "basic_boolean",
                    prop_description="Pre OS re-install.",
                    required=False,
                    configuration=False
                ),
        ))
        self.manager.register_item_type(ItemType("snapshot-base",
                timestamp=Property('basic_string'),
                active=Property('basic_string', default='true'),
            )
        )

        root = self.manager.create_root_item("root")
        rhel = self.manager.create_item("os-profile",
            "/software/profiles/rhel", name="rhel")
        dep = self.manager.create_item("deployment", "/deployments/d1")
        vim = self.manager.create_item("package", "/software/items/vim",
            name="vim")
        wget = self.manager.create_item("package", "/software/items/wget",
            name="wget")
        self.manager.create_item("node", "/deployments/d1/nodes/{0}".format(nodes[0]),
            hostname=nodes[0], custom_name="original_name")
        self.manager.create_inherited(vim.get_vpath(),
            "/deployments/d1/nodes/{0}/packages/vim".format(nodes[0]))
        self.manager.create_inherited(rhel.get_vpath(),
                                      "/deployments/d1/nodes/{0}/os".format(nodes[0]))
        self.manager.create_item("node", "/deployments/d1/nodes/{0}".format(nodes[1]),
            hostname=nodes[1], custom_name="original_name")

    def test_failed_property_validation_skips_other_validation(self):
        self._setUp_model_for_property_validation_tests()
        self.manager.create_item("infrastructure", "/infrastructure")
        # Previously would return 2 val errors for subnet, regex and invalid value for subnet
        output = self.manager.create_item("network", "/infrastructure/networking/networks/data",
                name="::/ \data", subnet="fe80::/64", dummy_bool="123")
        # Assert that only one ValidationError was returned for 'subnet' PropertyType
        prop_names = [er.property_name for er in output]
        self.assertEqual(1, prop_names.count("subnet"))
        validation_error = output[2].to_dict()
        self.assertEqual(validation_error['property_name'], 'subnet')
        self.assertEqual(validation_error['message'],
                "Invalid value 'fe80::/64'.")
        self.assertEqual(validation_error['error'], 'ValidationError')
        # Assert 'regex_error_desc' for 'dummy_bool' property works
        dummy_bool_error = output[0].to_dict()
        self.assertEqual(dummy_bool_error['property_name'], 'dummy_bool')
        self.assertEqual(dummy_bool_error['message'],
                "Invalid value '123'. Some error description.")
        self.assertEqual(dummy_bool_error['error'], 'ValidationError')

    def test_failed_prop_val_skips_item_type_validation(self):
        self._setUp_model_for_property_validation_tests()
        output = self.manager.create_item("ms", "/ms", hostname="123")
        # Assert that if there was property validation errors,
        # then ItemType validation was skipped
        prop_names = [er.property_name for er in output]
        self.assertEqual(1, prop_names.count("hostname"))
        validation_error = output[0].to_dict()
        self.assertEqual(validation_error['property_name'], 'hostname')
        self.assertEqual(validation_error['message'],
                "Invalid value: '123' is digit ")
        self.assertEqual(validation_error['error'], 'ValidationError')

    def test_set_all_applied_exceptions(self):
        self._create_deployment_and_a_couple_of_nodes()
        all_items = ["/software/profiles/rhel",
                     "/deployments/d1",
                     "/software/items/vim",
                     "/software/items/wget",
                     "/deployments/d1/nodes/node1",
                     "/deployments/d1/nodes/node1/packages/vim",
                     "/deployments/d1/nodes/node1/os",
                     "/deployments/d1/nodes/node2"]
        for vpath in all_items:
            self.assertTrue(self.manager.get_item(vpath).is_initial())
        # no exceptions
        self.manager.set_all_applied()
        for vpath in all_items:
            self.assertTrue(self.manager.get_item(vpath).is_applied())
        # reset
        for vpath in all_items:
            self.manager.get_item(vpath).set_initial()
        for vpath in all_items:
            self.assertTrue(self.manager.get_item(vpath).is_initial())
        # create exception and test it
        self.manager.create_item('snapshot-base', '/snapshots/snapshot')

        self.manager.set_all_applied(exceptions=['snapshot-base'])
        for vpath in all_items:
            self.assertTrue(self.manager.get_item(vpath).is_applied())
        self.assertTrue(self.manager.get_item('/snapshots/snapshot').is_initial())

    def prepare_items_for_restore_test(self):
        self._create_deployment_and_a_couple_of_nodes()
        # Create items in all different states
        self.manager.get_item('/deployments/d1').set_for_removal()
        self.manager.get_item('/deployments/d1/nodes/node1/packages/vim').set_removed()
        self.manager.get_item('/software/items/vim').set_updated()
        self.manager.get_item('/deployments/d1/nodes/node1').set_initial()
        self.manager.get_item('/deployments/d1/nodes/node1').set_applied()
        self.assertEqual(
            {'hostname': 'node1', 'custom_name': 'original_name'},
            self.manager.get_item("/deployments/d1/nodes/node1").get_applied_properties())

    def test_handle_prepare_for_restore_sets_to_initial(self):
        """
        Test set_required_to_initial works at all (no excluded_paths used)
        1. create items in different states
        2. restore all
        3. check that everything in Initial state
        """
        # 1.
        self.prepare_items_for_restore_test()
        # Check after prepare for restore all are set back to Initial state
        # 2.
        self.assertEqual(None, self.manager.set_items_to_initial_from("/"))
        # 3.
        self.assertEqual('Initial', self.manager.get_item("/software/profiles/rhel").get_state())
        self.assertEqual('Initial', self.manager.get_item("/deployments/d1").get_state())
        self.assertEqual('Initial', self.manager.get_item("/software/items/vim").get_state())
        self.assertEqual('Initial', self.manager.get_item("/deployments/d1/nodes/node1").get_state())
        self.assertEqual('Initial', self.manager.get_item("/deployments/d1/nodes/node1/packages/vim").get_state())
        self.assertEqual('Initial', self.manager.get_item("/deployments/d1/nodes/node1/os").get_state())
        self.assertEqual('Initial', self.manager.get_item("/deployments/d1/nodes/node2").get_state())
        self.assertEqual(
            {},
            self.manager.get_item("/deployments/d1/nodes/node1").get_applied_properties())

    def test_handle_prepare_for_restore_sets_to_initial_with_exclude_paths(self):
        """
        Test set_required_to_initial respects excluded_paths
        1. create items in different states
        2. restore_all with exclusions
        3. check that:
          a. everything but excluded state is in state Initial
          b. excluded item paths has original state set in 1.
        """
        # 1.
        self.prepare_items_for_restore_test()
        # 2.
        self.manager.set_items_to_initial_from(
            "/",
            ["/deployments/d1/nodes/node1/packages/",
             "/software/items"])
        # 3.
        self.assertEqual('Initial', self.manager.get_item("/software/profiles/rhel").get_state())
        self.assertEqual('Initial', self.manager.get_item("/deployments/d1").get_state())
        self.assertEqual('Updated', self.manager.get_item("/software/items/vim").get_state())
        self.assertEqual('Initial', self.manager.get_item("/deployments/d1/nodes/node1").get_state())
        self.assertEqual('Removed', self.manager.get_item("/deployments/d1/nodes/node1/packages/vim").get_state())
        self.assertEqual('Initial', self.manager.get_item("/deployments/d1/nodes/node1/os").get_state())
        self.assertEqual('Initial', self.manager.get_item("/deployments/d1/nodes/node2").get_state())
        self.assertEqual(
            {},
            self.manager.get_item("/deployments/d1/nodes/node1").get_applied_properties())

    def test_handle_prepare_for_restore_item_bad_path(self):
        self.assertRaises(ModelManagerException,
                          self.manager.set_items_to_initial_from,
                          '/bad/path')

    def test_recreate_removed_previously_updated_item(self):
        # Recreate with applied properties
        self._create_deployment_and_a_couple_of_nodes()
        node = self.manager.query_by_vpath("/deployments/d1/nodes/node1")
        node.set_applied()
        node.update_properties({'custom_name': "updated_name"})
        self.assertEqual(ModelItem.Updated, node.get_state())
        self.manager.remove_item(node.vpath)
        self.assertEqual(ModelItem.ForRemoval, node.get_state())
        self.manager.create_item("node", "/deployments/d1/nodes/node1",
            hostname="node1", custom_name="original_name")
        self.assertEqual(ModelItem.Applied, node.get_state())
        self.assertEqual("original_name", node.custom_name)
        # Recreate with updated properties
        node.update_properties({'custom_name': "updated_name"})
        self.assertEqual(ModelItem.Updated, node.get_state())
        self.manager.remove_item(node.vpath)
        self.assertEqual(ModelItem.ForRemoval, node.get_state())
        self.manager.create_item("node", "/deployments/d1/nodes/node1",
            hostname="node1", custom_name="updated_name")
        self.assertEqual(ModelItem.Updated, node.get_state())
        self.assertEqual("updated_name", node.custom_name)

    def test_query_item_applied_properties_determinable(self):
        # Same tests as in test_model_item, but testing the QueryItem here
        # 7855 AC 1. - New model item created, no plan run
        self._create_deployment_and_a_couple_of_nodes()
        node = self.manager.query_by_vpath("/deployments/d1/nodes/node1")
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
        # 7855 AC 2. - ModelItem set to applied state
        self.assertEqual(False, node.applied_properties_determinable)
        node.set_applied()
        self.assertEqual(True, node.applied_properties_determinable)

    def test_query_item_applied_properties_determinable_2(self):
        # Same tests as in test_model_item, but testing the QueryItem here
        self._create_deployment_and_a_couple_of_nodes()
        node = self.manager.query_by_vpath("/deployments/d1/nodes/node1")
        # 7855 AC 7 - ForRemoval, flag is false, recreate item - was Initial
        node._set_applied_properties_determinable(False)
        self.manager.remove_item(node.vpath)
        # 20150417
        #self.assertEqual(ModelItem.ForRemoval, node.get_state())
        self.manager.create_item("node", "/deployments/d1/nodes/node1",
            hostname="node1", custom_name="original_name")
        self.assertEqual(ModelItem.Initial, node.get_state())
        self.assertEqual("original_name", node.custom_name)
        # 7855 AC 7 - ForRemoval, flag is false, recreate item - was Updated
        node.set_applied()
        node.update_properties({'custom_name': "updated_name"})
        node._set_applied_properties_determinable(False)
        self.assertEqual(ModelItem.Updated, node.get_state())
        self.manager.remove_item(node.vpath)
        # 20150417
        #self.assertEqual(ModelItem.ForRemoval, node.get_state())
        self.manager.create_item("node", "/deployments/d1/nodes/node1",
            hostname="node1", custom_name="original_name")
        self.assertEqual(ModelItem.Updated, node.get_state())
        self.assertEqual("original_name", node.custom_name)
        # 7855 AC 7 - ForRemoval, flag is false, recreate item - was Applied
        node.set_applied()
        self.manager.remove_item(node.vpath)
        node._set_applied_properties_determinable(False)
        self.assertEqual(ModelItem.ForRemoval, node.get_state())
        self.manager.create_item("node", "/deployments/d1/nodes/node1",
            hostname="node1", custom_name="original_name")
        self.assertEqual(ModelItem.Updated, node.get_state())
        self.assertEqual("original_name", node.custom_name)

    def test_query_item_applied_properties_determinable_3(self):
        # Same tests as in test_model_item, but testing the QueryItem here
        self._create_deployment_and_a_couple_of_nodes()
        node = self.manager.query_by_vpath("/deployments/d1/nodes/node1")
        # 7855 AC 9 - Initial item, flag is true, item removed
        self.assertEqual(ModelItem.Initial, node.get_state())
        self.assertEqual(True, node.applied_properties_determinable)
        self.manager.remove_item(node.vpath)
        self.assertEqual(ModelItem.Removed, node.get_state())
        self.assertRaises(ModelManagerException, self.manager.query_by_vpath, node.vpath)
        # 7855 AC 10 - Initial item, flag is false, item removed
        node2 = self.manager.query_by_vpath("/deployments/d1/nodes/node2")
        node2._set_applied_properties_determinable(False)
        self.assertEqual(ModelItem.Initial, node2.get_state())
        self.assertEqual(False, node2.applied_properties_determinable)
        self.manager.remove_item(node2.vpath)
        # 20150417
        #self.assertEqual(ModelItem.ForRemoval, node2.get_state())

    def test_inherit_item_no_source(self):
        # LITPCDS-9340
        self._create_deployment_and_a_couple_of_nodes()
        node3 = self.manager.create_item("node", "/deployments/d1/nodes/node3",
            hostname="node3", custom_name="original_name")

        source = self.manager.query_by_vpath("/software/items/vim")
        inherited_vim = self.manager.query_by_vpath("/deployments/d1/nodes/node1/packages/vim")
        # Test double inheritance
        dbl_inherited_vim = self.manager.create_inherited(inherited_vim.get_vpath(),
                "/deployments/d1/nodes/node2/packages/vim")
        # Test triple inheritance (dbl_inherit_vim is now also a source)
        tri_inherited_vim = self.manager.create_inherited(dbl_inherited_vim.get_vpath(),
                "/deployments/d1/nodes/node3/packages/vim")
        self.manager.set_all_applied()
        self.manager.remove_item(dbl_inherited_vim.get_vpath())
        self.manager.remove_item(inherited_vim.get_vpath())
        self.manager.remove_item(source.get_vpath())
        # Can't remove source items, as they have inherited items which are not removed
        self.assertRaises(ModelManagerException, self.manager._delete_removed_item, inherited_vim)
        self.assertRaises(ModelManagerException, self.manager._delete_removed_item, dbl_inherited_vim)
        # Assert no error raised when not removing a source
        self.manager._delete_removed_item(tri_inherited_vim)

    def _create_deployment_with_many_clusters(self, num_clusters, num_nodes):
        self.manager.register_item_type(ItemType("root",
            software=Child("software", required=True),
            deployments=Collection("deployment"),
            ms=Child("node", required=True),
        ))

        self.manager.register_item_type(ItemType("deployment",
            clusters=Collection("cluster"),
            ordered_clusters=View("basic_list",
                callable_method=CoreExtension.get_ordered_clusters),
        ))

        self.manager.register_item_type(ItemType("cluster-base",
            ))
        self.manager.register_item_type(ItemType("cluster",
            extend_item="cluster-base",
            nodes=Collection("node"),
            dependency_list=Property("basic_string", default="",
                updatable_rest=True),
        ))

        self.manager.register_item_type(ItemType("package",
            name=Property("basic_string"),
        ))
        self.manager.register_item_type(ItemType("software",
            profiles=Collection("os-profile"),
            items=Collection("package"),
        ))
        self.manager.register_item_type(ItemType("os-profile",
            name=Property("basic_string"),
        ))
        self.manager.register_item_type(ItemType("node",
            hostname=Property("basic_string", required=True),
            os=Reference("os-profile"),
            packages=RefCollection("package"),
            upgrade=Child("upgrade"),
            custom_name=Property("basic_string"),
        ))

        ########
        root = self.manager.create_root_item("root")
        dep = self.manager.create_item("deployment", "/deployments/d1")

        for cluster_id in xrange(num_clusters):
            cluster_vpath = "/deployments/d1/clusters/cluster_{0:0>2d}".format(cluster_id)
            cluster = self.manager.create_item( "cluster", cluster_vpath)

            for node_id in xrange(num_nodes):
                node_hostname = "node_{0:0>2d}".format(node_id)
                node_vpath = "/".join([cluster_vpath, "nodes", node_hostname])
                node = self.manager.create_item(
                    "node", node_vpath, hostname=node_hostname,
                    custom_name="foo")

    def test_cluster_ordering_circular_dependency(self):
        self._create_deployment_with_many_clusters(3, 2)
        deployment = QueryItem(self.manager,
                               self.manager.query('deployment')[0])

        non_ms_nodes = [ node for node in self.manager.query("node") if
                node.vpath != "/ms" ]
        self.assertEquals(6, len(non_ms_nodes))

        clusters = self.manager.query("cluster")
        clusters.sort(key=lambda c: c.item_id)
        self.assertEquals(3, len(clusters))
        clusters[0].set_property("dependency_list", "cluster_01,cluster_02")
        clusters[1].set_property("dependency_list", "cluster_02")
        clusters[2].set_property("dependency_list", "cluster_00")

        try:
            deployment.ordered_clusters
        except ViewError as exc:
            err_msg = str(exc)
            self.assertTrue(err_msg.startswith("A cyclic dependency exists in graph"))
        else:
            assert False, '"ViewError" should have been raised'

    def test_cluster_ordering_invalid_cluster_dependency(self):
        self._create_deployment_with_many_clusters(3, 2)
        deployment = QueryItem(self.manager,
                               self.manager.query('deployment')[0])

        clusters = self.manager.query("cluster")
        clusters.sort(key=lambda c: c.item_id)
        self.assertEquals(3, len(clusters))
        clusters[1].set_property("dependency_list", "not_a_valid_cluster")

        try:
            deployment.ordered_clusters
        except ViewError as exc:
            self.assertTrue("Unknown cluster with id='not_a_valid_cluster'"
                    in str(exc))
        else:
            assert False, '"ViewError" should have been raised'

    def test_cluster_ordering_invalid_dependency_on_itself(self):
        self._create_deployment_with_many_clusters(3, 2)
        deployment = QueryItem(self.manager,
                               self.manager.query('deployment')[0])

        clusters = self.manager.query("cluster")
        clusters.sort(key=lambda c: c.item_id)
        self.assertEquals(3, len(clusters))
        clusters[1].set_property("dependency_list", "cluster_01")

        try:
            deployment.ordered_clusters
        except ViewError as exc:
            self.assertTrue("A cluster cannot depend on itself" in str(exc))
        else:
            assert False, '"ViewError" should have been raised'

    def test_cluster_ordering_invalid_dependency_another_repeated(self):
        self._create_deployment_with_many_clusters(3, 2)
        deployment = QueryItem(self.manager,
                               self.manager.query('deployment')[0])

        clusters = self.manager.query("cluster")
        clusters.sort(key=lambda c: c.item_id)
        self.assertEquals(3, len(clusters))
        clusters[1].set_property("dependency_list", "cluster_02,cluster_02")

        try:
            deployment.ordered_clusters
        except ViewError as exc:
            expected = ('Only one occurrence of a cluster is allowed in '
                        '"dependency_list" property. The following clusters '
                        'are repeated: cluster_02')
            self.assertTrue(expected in str(exc))
        else:
            assert False, '"ViewError" should have been raised'

    def test_cluster_ordering_circular_invalid_itself_repeat_dependcency(self):
        self._create_deployment_with_many_clusters(6,2)
        deployment = QueryItem(self.manager,
                               self.manager.query('deployment')[0])

        non_ms_nodes = [ node for node in self.manager.query("node") if
                node.vpath != "/ms" ]
        self.assertEquals(12, len(non_ms_nodes))

        clusters = self.manager.query("cluster")
        clusters.sort(key=lambda c: c.item_id)
        self.assertEquals(6, len(clusters))

        # circular dependancy
        clusters[0].set_property("dependency_list", "cluster_01,cluster_02")
        clusters[1].set_property("dependency_list", "cluster_02")
        clusters[2].set_property("dependency_list", "cluster_00")

        # invalid index
        clusters[3].set_property("dependency_list", "not_a_valid_cluster")

        # depend on itself
        clusters[4].set_property("dependency_list", "cluster_04")

        # repeated dependancy
        clusters[5].set_property("dependency_list", "cluster_02,cluster_02")

        try:
            deployment.ordered_clusters
        except ViewError as exc:
            self.assertTrue("A cyclic dependency exists in graph"
                    in str(exc))

            self.assertTrue("Unknown cluster with id='not_a_valid_cluster'"
                    in str(exc))

            self.assertTrue("A cluster cannot depend on itself" in str(exc))

            expected_rep = ('Only one occurrence of a cluster is allowed in '
                        '"dependency_list" property. The following clusters '
                        'are repeated: cluster_02')
            self.assertTrue(expected_rep in str(exc))
        else:
            assert False, '"ViewError" should have been raised'

    def test_cluster_ordering(self):
        self._create_deployment_with_many_clusters(3, 2)
        deployment = QueryItem(self.manager,
                               self.manager.query('deployment')[0])

        non_ms_nodes = [ node for node in self.manager.query("node") if
                node.vpath != "/ms" ]
        self.assertEquals(6, len(non_ms_nodes))

        clusters = self.manager.query("cluster")
        clusters.sort(key=lambda c: c.item_id)
        self.assertEquals(3, len(clusters))

        clusters[0].set_property("dependency_list", "")
        clusters[1].set_property("dependency_list", "cluster_02")
        clusters[2].set_property("dependency_list", "cluster_00")
        clusters = [QueryItem(self.manager, mi) for mi in clusters]

        sorted_clusters = deployment.ordered_clusters
        self.assertTrue(isinstance(sorted_clusters, list))
        self.assertTrue(all(isinstance(qi, QueryItem) for qi in sorted_clusters))

        self.assertEquals(3, len(sorted_clusters))
        self.assertEquals([clusters[0], clusters[2], clusters[1]], sorted_clusters)

    def test_cluster_ordered_and_unordered(self):
        self._create_deployment_with_many_clusters(10, 2)
        deployment = QueryItem(self.manager,
                               self.manager.query('deployment')[0])

        non_ms_nodes = [ node for node in self.manager.query("node") if
                node.vpath != "/ms" ]
        self.assertEquals(20, len(non_ms_nodes))

        clusters = self.manager.query("cluster")
        clusters.sort(key=lambda c: c.item_id)
        self.assertEquals(10, len(clusters))

        clusters[0].set_property("dependency_list", "cluster_08")
        clusters[1].set_property("dependency_list", "cluster_00")
        clusters[2].set_property("dependency_list", "cluster_01")
        clusters[3].set_property("dependency_list", "cluster_01")
        clusters[4].set_property("dependency_list", "cluster_01")
        clusters = [QueryItem(self.manager, mi) for mi in clusters]

        sorted_clusters = deployment.ordered_clusters
        self.assertTrue(isinstance(sorted_clusters, list))
        self.assertTrue(all(isinstance(qi, QueryItem) for qi in sorted_clusters))

        self.assertEquals(10, len(sorted_clusters), sorted_clusters)
        expected_cluster_order = [
                clusters[8], clusters[0], clusters[1], clusters[2],
                clusters[3], clusters[4],

                clusters[5], clusters[6], clusters[7], clusters[9]
        ]
        self.assertEquals(expected_cluster_order, sorted_clusters)

    def test_future_property_value_comparison(self):
        # Priority: 1. value, 2. query_item, 3. property_name
        self._create_deployment_and_a_couple_of_nodes()
        node = self.manager.query_by_vpath("/deployments/d1/nodes/node1")
        node2 = self.manager.query_by_vpath("/deployments/d1/nodes/node2")
        fpv1 = FuturePropertyValue(node, "hostname")
        fpv2 = FuturePropertyValue(node2, "hostname")
        fpv3 = FuturePropertyValue(node2, "custom_name")
        fpv4 = FuturePropertyValue(node, "hostname")
        fpv6 = FuturePropertyValue(node2, "custom_name")
        fpv7 = FuturePropertyValue(node, "custom_name")

        # Compare FuturePropertyValue instances
        # Different query_items, value and prop_name same
        self.assertTrue(fpv1 < fpv2) # '../node2' > '../node1'
        self.assertTrue(fpv2 > fpv1)
        self.assertTrue(fpv1 != fpv2)
        self.assertTrue(fpv2 != fpv1)

        # Different value and property_name, same query_item
        self.assertTrue(fpv3 > fpv2) # 'original_name' > 'node2'
        self.assertTrue(fpv2 < fpv3)
        self.assertTrue(fpv2 != fpv3)
        self.assertTrue(fpv3 != fpv2)

        # Same value, query_item and property_name
        self.assertTrue(fpv1 == fpv4) # Same
        self.assertTrue(fpv4 == fpv1)
        self.assertEqual(cmp(fpv1, fpv4), 0)
        self.assertEqual(cmp(fpv4, fpv1), 0)

        # Different property_name, same value and query_item
        self.manager.update_item(node2.get_vpath(), hostname='original_name')
        self.assertEqual(node2.hostname, node2.custom_name)
        self.assertTrue(fpv2 > fpv3) # 'hostname' >  'custom_name'
        self.assertTrue(fpv3 < fpv2)
        self.assertTrue(fpv2 != fpv3)
        self.assertTrue(fpv3 != fpv2)

        # Compare 'value' property of instance (string)
        self.assertTrue(fpv1 < 'node2') # 'node1' < 'node2'
        self.assertTrue('node2' > fpv1)
        self.assertTrue(fpv1 == 'node1')
        # Same with unicode unicode value
        self.manager.update_item(node2.get_vpath(), custom_name=u'NEW_NAME')
        self.assertTrue(fpv3 == fpv6.value) # u'NEW_NAME' == u'NEW_NAME'
        self.assertTrue(fpv3 < 'original_name')# u'NEW_NAME' < 'original_name'
        self.assertTrue(fpv3 > u'NEW') # u'NEW_NAME' > u'NEW'

        # LITPCDS-9566: Test sorted() on list of FPVs like in lvm.py
        self.manager.update_item(node.get_vpath(), custom_name=u'$::disk_abcd_dev')
        self.manager.update_item(node2.get_vpath(), custom_name=u'$::disk_efgh_dev')
        pv = [fpv7, fpv6]
        pv2 = [fpv6, fpv7]
        self.assertTrue(pv != pv2)
        self.assertTrue(sorted(pv) == sorted(pv2))
        pv3 = [fpv7, fpv6, fpv1]
        self.assertTrue(sorted(pv) != sorted(pv3))

        # Compare against None
        self.assertTrue(fpv1 > None)
        self.assertTrue(None < fpv1)
        self.assertTrue(fpv1 != None)
        self.assertTrue(None != fpv1)

    def test_do_not_check_if_collections_are_deprecated(self):
        # LITPCDS-11066
        model = ModelManager()
        model.register_item_type(ItemType(
            "root",
            container=Child("container"))
        )

        model.register_item_type(ItemType(
            "container",
            triggers=Collection("vcs-trigger"),
            ref_triggers=RefCollection("vcs-trigger"))
        )

        model.register_item_type(ItemType(
            "vcs-trigger",
             deprecated=True,)
        )

        model.create_root_item("root")
        container = model.create_item("container", "/container")
        triggers = model.get_item('/container/triggers')
        ref_triggers = model.get_item('/container/ref_triggers')

        model._check_type_deprecation = mock.Mock()
        # Do not check if collections are deprecated
        model.check_model_item_deprecation(triggers)
        self.assertFalse(model._check_type_deprecation.called)

        # Do not check if RefCollections are deprecated
        model.check_model_item_deprecation(ref_triggers)
        self.assertFalse(model._check_type_deprecation.called)

        # But does for other items
        model.check_model_item_deprecation(container)
        self.assertTrue(model._check_type_deprecation.called)

    def test_litpcds_11328_updatable_rest_false_on_inherited_item(self):
        self._create_sibbling_structure()
        source_item = self.manager.get_item("/some_item")
        source_item = self.manager.update_item(
                "/some_item", name="SHOULD_NOT_BE_UPDATED")
        self.assertTrue(source_item.is_initial())
        inherited_item = self.manager.get_item('/item/some_item')
        inherited_item.set_applied()
        self.assertTrue(inherited_item.is_applied())
        expected_error = {
                'message': 'Unable to modify readonly property: name',
                'uri': '/item/some_item',
                'property_name': 'name',
                'error': 'InvalidRequestError'}

        # Test updating the source item
        errors = self.manager.update_item(
                "/some_item", name="my_new_name")
        self.assertFalse(isinstance(errors, ModelItem),
                "Expected a list of errors, got a ModelItem.")
        self.assertTrue(
                any(error.to_dict() == expected_error for error in errors),
                "No expected error found: {0}".format(expected_error))
        self.assertEquals(source_item.get_merged_properties()['name'],
                "SHOULD_NOT_BE_UPDATED")
        self.assertEquals(source_item.get_merged_properties()['name'],
                "SHOULD_NOT_BE_UPDATED")

        # Test updating the inherited item
        errors = self.manager.update_item(
                "/item/some_item", name="my_new_name")
        self.assertFalse(isinstance(errors, ModelItem),
                "Expected a list of errors, got a ModelItem.")
        self.assertTrue(
                any(error.to_dict() == expected_error for error in errors),
                "No expected error found: {0}".format(expected_error))
        self.assertEquals(source_item.get_merged_properties()['name'],
                "SHOULD_NOT_BE_UPDATED")
        self.assertEquals(inherited_item.get_merged_properties()['name'],
                "SHOULD_NOT_BE_UPDATED")

    def test_update_item_with_empty_string(self):
        # LITPCDS-11647
        model = ModelManager()
        model.register_property_types([
            PropertyType("basic_string", regex=r"^[a-zA-Z0-9\-\._]+$"),
            PropertyType("basic_list",
                         regex=r"^[a-zA-Z0-9\-\._]*(,[a-zA-Z0-9\-\._]+)*$"),
            ])
        model.register_item_type(ItemType(
            "root",
            services=Collection("vcs-clustered-service")
        ))
        model.register_item_type(ItemType(
            "vcs-clustered-service",
            dependency_list=Property("basic_list"),
            non_empty_prop=Property("basic_string")
        ))
        model.create_root_item("root")
        item = model.create_item("vcs-clustered-service", "/services/CS_VM1",
                dependency_list="")
        self.assertEqual(item.properties['dependency_list'], "")
        # Update with empty string -> doesn't delete property
        model._update_item(item.vpath, {u'dependency_list': u''})
        self.assertEqual(item.properties['dependency_list'], "")
        model._update_item(item.vpath, {u'dependency_list': u'foobar'})
        self.assertEqual(item.properties['dependency_list'], "foobar")
        model._update_item(item.vpath, {'dependency_list': ''})
        self.assertEqual(item.properties['dependency_list'], "")

        # Try to update a property with empty string that doesn't match regex
        res = model._update_item(item.vpath, {'non_empty_prop': ''})
        self.assertEqual(len(res), 1)
        self.assertTrue(type(res[0]) is ValidationError)
        self.assertFalse('non_empty_prop' in item.properties)


    def test_recursive_check_child_source_for_removal(self):
        model = ModelManager()
        model.register_item_type(ItemType(
            "root",
            item=Child("item"),
            source=Child("other-item"),
        ))
        model.register_item_type(ItemType(
            "item",
            ref=Reference("other-item"),
            items=Collection("item")
        ))
        model.register_item_type(ItemType("other-item"))

        model.create_root_item("root")
        source = model.create_item("other-item", "/source")
        model.create_item("item", "/item")
        parent = model.get_item("/item")
        model.create_item("item", "/item/items/item1")
        model.create_item("item", "/item/items/item1/items/item11")
        model.create_item("item", "/item/items/item1/items/item12")
        model.create_item("item", "/item/items/item2")
        model.create_item("item", "/item/items/item2/items/item21")
        model.create_item("item", "/item/items/item2/items/item22")
        ref = model.create_inherited("/source",
            "/item/items/item2/items/item22/ref")
        model.set_all_applied()

        source.set_for_removal()
        self.assertEqual(source.get_state(), ModelItem.ForRemoval)
        error = model.check_child_source_item_not_for_removal(parent, "/item")
        self.assertTrue("Item has a descendant whose source item is marked for removal",
                error.error_message)

        model.set_all_applied()
        no_error = model.check_child_source_item_not_for_removal(parent, "/item")
        self.assertFalse(isinstance(no_error, ValidationError))
        self.assertEquals(None, no_error)

    def test_check_has_failed_removal(self):
        model = ModelManager()
        model.register_item_type(ItemType(
            "root",
            item=Child("item"),
        ))
        model.create_root_item("root")
        model.register_item_type(ItemType("item"))
        item = model.create_item("item", "/item")
        self.assertEqual(None, model.check_has_failed_removal(item))
        item.set_applied()
        self.assertEqual(None, model.check_has_failed_removal(item))
        item.set_updated()
        self.assertEqual(None, model.check_has_failed_removal(item))
        item.set_for_removal()
        self.assertEqual(None, model.check_has_failed_removal(item))
        item.set_removed()
        self.assertEqual(None, model.check_has_failed_removal(item))
        # Mimic removal failure in a plan (LITPCDS-12017)
        item.set_for_removal()
        error = model.check_has_failed_removal(item)
        self.assertTrue(type(error) is ValidationError)
        item.set_updated()
        self.assertEqual(None, model.check_has_failed_removal(item))

    def test_validate_create_item_no_default_property(self):
        # LITPCDS-13781: Include default properties for create validation
        model = ModelManager()
        model.validator = mock.Mock(validate_properties=mock.Mock(return_value=[]))
        model.register_property_type(PropertyType("basic_string"))
        model.register_item_type(ItemType(
            "root",
            item=Child("item"),
        ))
        model.register_item_type(ItemType("item",
            mode=Property('basic_string',
            default='foo'),
        ))

        model.create_root_item("root")
        model.validator.validate_properties.reset_mock()
        item = model.create_item("item", "/item")
        self.assertEqual({"mode": "foo"},
                model.validator.validate_properties.call_args[0][1])

    def test_get_complete_properties(self):
        # LITPCDS-13781: Include default properties for create validation
        item_type = ItemType("item",
            item_description="test item",
            prop_with_default=Property('basic_string',
                default='foo'),
            prop_without_default=Property('basic_string'),
            ref=Reference('root'))

        # litp create -p /item -t item
        complete = self.manager._get_complete_properties(item_type, {})
        self.assertEqual(complete, {'prop_with_default': 'foo'})
        # litp create -p /item -t item -o prop_without_default='bar'
        complete = self.manager._get_complete_properties(item_type,
                {'prop_without_default': 'bar'})
        self.assertEqual(complete, {'prop_without_default': 'bar',
                'prop_with_default': 'foo'})
        # litp create -p /item -t item -o prop_without_default='bar' \
        #       prop_with_default='foo'
        complete = self.manager._get_complete_properties(item_type,
                {'prop_without_default': 'bar', 'prop_with_default':'foo'})
        self.assertEqual(complete, {'prop_without_default': 'bar',
                'prop_with_default': 'foo'})
        # litp create -p /item -t item -o prop_without_default='bar' \
        #       prop_with_default='eggs'
        complete = self.manager._get_complete_properties(item_type,
                {'prop_without_default': 'bar', 'prop_with_default':'eggs'})
        self.assertEqual(complete, {'prop_without_default': 'bar',
                'prop_with_default': 'eggs'})

    def test_force_debug(self):
        # TORF-161280: Fix force_debug
        self.manager.register_item_type(ItemType(
            "root",
            litp=Child("litp", required=True),
        ))
        self.manager.register_item_type(ItemType(
            "litp",
            logging=Child("logging", required=True),
        ))
        self.manager.register_item_type(ItemType(
            "logging",
            force_debug=Property("basic_string", required=True, default="false"),
        ))
        self.manager.create_root_item("root")
        logging_item = self.manager.get_item('/litp/logging')

        # TC 01: Update logging ModelItem force_debug='true' => 10/DEBUG
        with mock.patch('litp.core.model_manager.SafeConfigParser') as mock_parser_class:
            parser_instance = mock_parser_class.return_value
            with mock.patch('litp.core.model_manager.log.trace.setLevel') as mock_setLevel:
                result = self.manager.force_debug(True, normal_start=False)
                # DEBUG forced on
                expected = [mock.call(10)]
                self.assertEqual(mock_setLevel.call_args_list, expected)
                # Config file not read
                self.assertEqual(None, result)
                self.assertFalse(mock_parser_class.called)
                # Logging model item property not reset
                with mock.patch('litp.core.model_manager.ModelManager.update_item') as mock_update:
                    self.assertFalse(mock_update.called)

        # TC 02: INFO config file, update item force_debug='false' => 20/INFO
        with mock.patch('litp.core.model_manager.SafeConfigParser') as mock_parser_class:
            parser_instance = mock_parser_class.return_value
            parser_instance.get.return_value = 'INFO'
            with mock.patch('litp.core.model_manager.log.trace.setLevel') as mock_setLevel:
                result = self.manager.force_debug(False, normal_start=False)
                # Config file read as debug not forced on
                self.assertTrue(mock_parser_class.called)
                # INFO level read from config file and used
                expected = [mock.call(20)]
                self.assertEqual(mock_setLevel.call_args_list, expected)

        # TC 03: DEBUG config file, update item force_debug='false' => 10/DEBUG
        with mock.patch('litp.core.model_manager.SafeConfigParser') as mock_parser_class:
            parser_instance = mock_parser_class.return_value
            parser_instance.get.return_value = 'DEBUG'
            with mock.patch('litp.core.model_manager.log.trace.setLevel') as mock_setLevel:
                result = self.manager.force_debug(False, normal_start=False)
                # Config file read as debug not forced on
                self.assertTrue(mock_parser_class.called)
                # DEBUG level read from config file and used
                expected = [mock.call(10)]
                self.assertEqual(mock_setLevel.call_args_list, expected)

        # TC 04: litpd service start, item has force_debug='true' and
        # INFO config file  => INFO & property reset
        self.manager.update_item("/litp/logging", force_debug="true")
        with mock.patch('litp.core.model_manager.SafeConfigParser') as mock_parser_class:
            parser_instance = mock_parser_class.return_value
            parser_instance.get.return_value = 'INFO'
            with mock.patch('litp.core.model_manager.log.trace.setLevel') as mock_setLevel:
                result = self.manager.force_debug(False, normal_start=True)
                # Config file read as debug not forced on
                self.assertTrue(mock_parser_class.called)
                # INFO level read from config file and used
                expected = [mock.call(20)]
                self.assertEqual(mock_setLevel.call_args_list, expected)
                # Logging model item property reset on startup
                self.assertEqual(logging_item.force_debug, 'false')

        # TC 05: Invalid level is specified in config file => returns exception
        with mock.patch('litp.core.model_manager.SafeConfigParser') as mock_parser_class:
            parser_instance = mock_parser_class.return_value
            parser_instance.get.return_value = 'FOOBARBAZ'
            result = self.manager.force_debug(False, normal_start=True)
            self.assertTrue(isinstance(result, ValidationError))
            self.assertEqual(result.error_message, "FOOBARBAZ is not a valid level option")

    def test_set_item_initial(self):
        self._create_deployment_and_a_couple_of_nodes(["node1", "node10"])
        self.manager.set_all_applied()

        node1 = self.manager.query_by_vpath("/deployments/d1/nodes/node1")
        node10 = self.manager.query_by_vpath("/deployments/d1/nodes/node10")

        self.assertTrue(node1.is_applied())
        self.assertTrue(node10.is_applied())

        exclude_paths = ['/ms',
                        '/plans',
                        '/snapshots',
                        '/litp/maintenance,',
                        '/litp/import-iso',
                        '/litp/restore_model',
                        '/litp/logging',
                        '/deployments/d1/nodes/node1']

        with mock.patch('litp.core.model_manager.log.trace.debug') as mock_logger:
            # Negative case
            self.manager._set_item_initial(node1, exclude_paths)
            self.assertFalse(mock_logger.called)
            self.assertTrue(node1.is_applied())
            self.assertTrue(node10.is_applied())

            # Positive case
            self.manager._set_item_initial(node10, exclude_paths)
            mock_logger.assert_called_once_with('set item to initial: %s', node10.vpath)
            self.assertTrue(node1.is_applied())
            self.assertTrue(node10.is_initial())
