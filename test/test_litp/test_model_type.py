'''
Created on Aug 14, 2013

@author: marco
'''
import unittest

from litp.core.validators import RegexValidator, IPAddressValidator
from litp.core.model_item import ModelItem
from litp.core.model_manager import ModelManager
from litp.core.model_type import PropertyType
from litp.core.model_type import Property
from litp.core.model_type import ItemType
from litp.core.model_type import Child
from litp.core.model_type import _BaseStructure
from litp.core.validators import ValidationError
from litp.core import constants


class Test(unittest.TestCase):

    def setUp(self):
        self.manager = ModelManager()

    def tearDown(self):
        pass

#    def test_child_item_requires(self):
#        item_type = ItemType("test1",
#            child1=Child("child", require="child2"),
#            child2=Child("child"),
#        )
#        child_type = ItemType("child")
#
#        self.manager.item_types["test1"] = item_type
#        self.manager.item_types["child"] = child_type
#
#        item_type.create_model_item(self.manager, "test1",
#                                                 "test1", {})
#

    def test_child_model_type_is_subclass_basetype(self):
        assert issubclass(Child, _BaseStructure)

    def test_validate_property_validator_regex(self):
        prop_type = PropertyType("basic_string",
                                 validators=[RegexValidator("^[0-9]+$")])
        basic_prop = Property('basic_string')
        basic_prop.prop_type = prop_type

        item_type = ItemType('package', name=basic_prop)

        test_props = {
            'name': 'foo',
        }
        result = self.manager.validator.validate_properties(item_type, test_props, "write")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].property_name, 'name')
        self.assertEqual(result[0].error_type, 'ValidationError')
        self.assertEqual(result[0].error_message,
            "Invalid value 'foo'.")

        test_props.update({'name': '123'})
        result = self.manager.validator.validate_properties(item_type, test_props, "write")
        self.assertEqual(len(result), 0)

    def test_validate_property_validator_ip_address_v6(self):
        prop_type = PropertyType("basic_string",
                                 validators=[IPAddressValidator("6")])
        basic_prop = Property('basic_string')
        basic_prop.prop_type = prop_type

        item_type = ItemType('package', address=basic_prop)

        test_props = {"address": 'foo'}
        result = self.manager.validator.validate_properties(item_type, test_props, "write")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].property_name, 'address')
        self.assertEqual(result[0].error_type, 'ValidationError')
        self.assertEqual(result[0].error_message,
                         "Invalid IPv6Address value 'foo'")

        test_props.update({'address': 'fe80::d267:e5ff:fe03'})
        result = self.manager.validator.validate_properties(item_type, test_props, "write")
        self.assertEqual(len(result), 0)

    def test_validate_property_validator_ip_address_v4(self):
        prop_type = PropertyType("basic_string",
                                 validators=[IPAddressValidator("4")])
        basic_prop = Property('basic_string')
        basic_prop.prop_type = prop_type

        item_type = ItemType('package', address=basic_prop)

        test_props = {"address": '300.300'}
        result = self.manager.validator.validate_properties(item_type, test_props, "write")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].property_name, 'address')
        self.assertEqual(result[0].error_type, 'ValidationError')
        self.assertEqual(result[0].error_message,
                         "Invalid IPAddress value '300.300'")

        test_props.update({'address': '172.19.29.123'})
        result = self.manager.validator.validate_properties(item_type, test_props, "write")
        self.assertEqual(len(result), 0)

    def test_validate_property_validator_ip_address_both(self):
        prop_type = PropertyType("basic_string",
                                 validators=[IPAddressValidator("both")])
        basic_prop = Property('basic_string')
        basic_prop.prop_type = prop_type

        item_type = ItemType('package', address=basic_prop)

        test_props = {"address": '300.300'}
        result = self.manager.validator.validate_properties(item_type, test_props, "write")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].property_name, 'address')
        self.assertEqual(result[0].error_type, 'ValidationError')
        self.assertEqual(result[0].error_message,
                         "Invalid IPAddress value '300.300'")

        test_props.update({'address': '172.19.29.123'})
        result = self.manager.validator.validate_properties(item_type, test_props, "write")
        self.assertEqual(len(result), 0)
        test_props.update({'address': 'fe80::d267:e5ff:fe03'})
        result = self.manager.validator.validate_properties(item_type, test_props, "write")
        self.assertEqual(len(result), 0)

    def test_property_eq(self):
        self.manager.register_item_type(ItemType("root",
            mockitem=Child("mock_item"),
        ))
        self.manager.create_root_item("root")
        prop_type = PropertyType("basic_boolean", regex="^true|false$")
        basic_prop = Property("basic_boolean")
        basic_prop.prop_type = prop_type
        self.manager.register_property_type(prop_type)
        item_type1 = ItemType('mock_item', value=basic_prop)
        self.manager.register_item_type(item_type1)
        self.assertEquals([
            ValidationError(property_name='value',
                error_message=("Invalid value 'True'."),
                )],
            self.manager.create_item("mock_item", "/mockitem", value="True"))
        expected_item = ModelItem(self.manager, item_type1, "mockitem", "/",
                properties={"value":"true"})
        create_item = self.manager.create_item("mock_item", "/mockitem", value="true")
        self.assertEquals(expected_item.show_item(), create_item.show_item())
