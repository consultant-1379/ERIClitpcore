from litp.core.extension import ModelExtension
from litp.core.model_type import ItemType
from litp.core.model_type import Property
from litp.core.model_type import PropertyType


class Bug7725Extension(ModelExtension):

    def define_property_types(self):
        # return a new property type test_name with regex validation
        return [
            PropertyType(
                'test_name_bug7725', regex=r'^.*$')
        ]

    def define_item_types(self):
        return [
            ItemType(
                'bug7725-sw-item',
                extend_item='software-item',
                name=Property('test_name_bug7725', default=''),
            )
        ]
