import unittest
import mock

from litp.core.model_type import Collection, View, RefCollection
from litp.core.model_item import ModelItem, CollectionItem
from litp.core.model_validator import ModelValidator
from litp.core.model_manager import ModelManager, QueryItem
from litp.core.model_type import Child, ItemType, Property, PropertyType, Reference
from litp.core.validators import ValidationError


class ModelValidatorTest(unittest.TestCase):
    def setUp(self):
        self.manager = mock.Mock(
            autospec='litp.core.model_manager.ModelManager')
        self.validator = ModelValidator(self.manager)

    def test_duplicate_validation_create_plan(self):
        # TORF-118147
        model = ModelManager()
        validator = ModelValidator(self.manager)
        model.register_item_type(ItemType(
            "root",
            ms=Child("ms"),
            sp=Child("storage-profile")
        ))
        model.register_item_type(ItemType(
            "ms",
            storage_profile=Reference("storage-profile")
        ))
        model.register_item_type(ItemType("storage-profile",
            child=Child("item")))
        model.register_item_type(ItemType("item"))
        root = model.create_root_item("root")
        ms = model.create_item("ms", "/ms")
        sp = model.create_item("storage-profile", "/sp")
        child = model.create_item("item", "/sp/child")
        in_sp = model.create_inherited("/sp", "/ms/storage_profile")

        original_validate = validator._validate_item_type_instance
        validator._validate_item_type_instance = mock.Mock(side_effect=original_validate)

        # call validate_item_type() with /ms
        validator.validate_item_type(ms.item_type, ms)
        # assert _validate_item_type_instance() was only called once
        self.assertEquals(1, validator._validate_item_type_instance.call_count)

    def test_collection_type_empty_no_min_count_validation(self):
        coll_item_type = mock.Mock(structure={}, validators=[])
        coll = Collection(coll_item_type)
        coll.children = {}
        coll.parent_vpath = None
        coll.vpath = '/item/coll'
        item_type = mock.Mock(structure={'coll': coll}, validators=[])
        self.manager.get_merged_properties.return_value = []
        item = ModelItem(self.manager, item_type, 'item', '/')
        self.manager.get_children.return_value={'coll': coll}
        errors = self.validator.validate_item_type(item_type, item)
        self.assertFalse(errors)

    def test_collection_type_failed_min_count_validation(self):
        coll_item_type = mock.Mock(structure={}, validators=[])
        coll = Collection(coll_item_type, min_count=1, max_count=10)
        coll.children = {}
        coll.parent_vpath = None
        coll.vpath = '/item/coll'
        item_type = mock.Mock(structure={'coll': coll}, validators=[])
        self.manager.get_merged_properties.return_value = []
        item = ModelItem(self.manager, item_type, 'item', '/')
        self.manager.get_children.return_value={'coll': coll}
        errors = self.validator.validate_item_type(item_type, item)
        self.assertTrue("This collection requires a minimum of 1 items "
                        "not marked for removal" in str(errors[0]))

    def test_collection_type_failed_max_count_validation(self):
        coll_item_type = mock.Mock(structure={}, validators=[])
        coll_item = CollectionItem(self.manager, coll_item_type, 'collitem',
                                   '/item/coll/collitem1')

        coll = Collection(coll_item_type, max_count=0)
        coll.children = {'coll_item': coll_item}
        coll.parent_vpath = None
        coll.vpath = '/item/coll'
        item_type = mock.Mock(structure={'coll': coll}, validators=[])
        self.manager.get_merged_properties.return_value = []
        item = ModelItem(self.manager, item_type, 'item', '/')
        self.manager.get_children.return_value={'coll': coll}
        errors = self.validator.validate_item_type(item_type, item)
        self.assertTrue("This collection is limited to a maximum of 0 items "
                        "not marked for removal" in str(errors[0]))

    def test_clear_property_validator(self):
        model = ModelManager()
        validator = ModelValidator(model)

        model.register_property_types([
            PropertyType("basic_string", regex=r"^[a-zA-Z0-9\-\._]+$"),
        ])
        model.register_item_type(ItemType(
            "root",
            container=Child("container"),
            source=Child("can-unset-two"),
        ))

        model.register_item_type(ItemType(
            "container",
            can_unset=Child("can-unset"),
            can_unset_two=Reference("can-unset-two"),
            can_unset_three=Child("can-unset-three"),
            cannot_unset=Child("cannot-unset"),
        ))
        model.register_item_type(ItemType(
            "can-unset",
            prop=Property("basic_string")
        ))
        model.register_item_type(ItemType(
            "can-unset-two",
            prop=Property("basic_string",
            )
        ))
        model.register_item_type(ItemType(
            "can-unset-three",
            prop=Property("basic_string",
                required=True,
                default='value',
            )
        ))
        model.register_item_type(ItemType(
            "cannot-unset",
            prop=Property("basic_string",
            required=True,
            )
        ))
        model.create_root_item("root")
        model.create_item("container", "/container")
        can_unset = model.create_item("can-unset", "/container/can_unset")
        can_unset_three = model.create_item("can-unset-three", "/container/can_unset_three")
        model.create_item("can-unset-two", "/source")
        can_unset_two = model.create_inherited("/source",
                "/container/can_unset_two")
        cannot_unset = model.create_item("cannot-unset",
                "/container/cannot_unset", prop='value')

        # Source, not required -> no errors (can be unset later)
        self.assertEqual([],
                validator._clear_property_validator(can_unset, 'prop'))

        # Inherit item -> no errors (reverts to source later)
        self.assertEqual([],
                validator._clear_property_validator(can_unset_two, 'prop'))

        # Source, required, with default -> no errors (reverts to default)
        self.assertEqual([],
                validator._clear_property_validator(can_unset_three, 'prop'))

        # Source, required, no default -> returns exception (can't be unset later)
        errors = validator._clear_property_validator(cannot_unset, 'prop')
        self.assertTrue(type(errors[0]) is ValidationError)

    def test_clashing_item_ids(self):
        # LITPCDS-13008: Extension item_ids conflict with ModelItem properties
        def view_callable(api, query_item):
            return 'foo'
        model = ModelManager()
        validator = ModelValidator(model)
        model.register_property_types([
            PropertyType("basic_string", regex=r"^[a-zA-Z0-9\-\._]+$"),
        ])
        model.register_item_type(ItemType(
            "root",
            container=Child("container"),
            container_two=Child("container-two"),
            source=Child("item"),
            source_two=Child("item-four"),
        ))
        model.register_item_type(ItemType(
            "container",
            parent=Reference("item"),
            source=Child("item-two"),
            children=Collection("item-three"), # LITPCDS-13008
            source_vpath=RefCollection("item-four"),
            vpath=View("basic_string", view_callable),
            #vvpath=View("basic_string", view_callable),
        ))
        model.register_item_type(ItemType(
            "container-two",
            children=Collection("item"), # empty
        ))
        model.register_item_type(ItemType(
            "item",
            name=Property("basic_string")
        ))
        model.register_item_type(ItemType(
            "item-two",
            name=Property("basic_string")
        ))
        model.register_item_type(ItemType(
            "item-three",
            name=Property("basic_string")
        ))
        model.register_item_type(ItemType(
            "item-four",
            name=Property("basic_string")
        ))

        model.create_root_item("root")
        container = model.create_item("container", "/container")
        container_two = model.create_item("container-two", "/container_two")
        model.create_item("item", "/source")
        model.create_item("item-four", "/source_two")
        c_source = model.create_item("item-two", "/container/source")
        model.create_item("item-three", "/container/children/child1")
        c_parent = model.create_inherited("/source", "/container/parent")
        model.create_inherited("/source_two", "/container/source_vpath/child1")

        # No unhandled Exceptions thrown or errors returned
        result = validator.validate_item_type(container.item_type, container)
        self.assertEqual(result, [])

        # Validate item with no children
        self.assertTrue(model._item_might_have_children(container_two))
        self.assertEqual(container_two.children['children'].children, {})
        result = validator.validate_item_type(container_two.item_type, container_two)
        self.assertEqual(result, [])

        # What TODO with Views?
        #container_qi = QueryItem(model, container)
        #self.assertEqual(container_qi.vpath, '/container')
        #self.assertEqual(container_qi.vvpath, 'foo')

        # Assert _validate_item_type_instance called with expected objects (not dict)
        validator._validate_item_type_instance = mock.Mock(return_value=[])
        validator.validate_item_type(container.item_type, container)
        c_source_vpath = model.get_item("/container/source_vpath")
        c_children = model.get_item("/container/children")
        expected = sorted([
                mock.call(c_parent.parent.item_type.structure[c_parent.item_id], c_parent),
                mock.call(c_source_vpath.parent.item_type.structure[c_source_vpath.item_id], c_source_vpath),
                mock.call(c_source.parent.item_type.structure[c_source.item_id], c_source),
                mock.call(c_children.parent.item_type.structure[c_children.item_id], c_children)
        ])
        self.assertEqual(sorted(validator._validate_item_type_instance.call_args_list), expected)
