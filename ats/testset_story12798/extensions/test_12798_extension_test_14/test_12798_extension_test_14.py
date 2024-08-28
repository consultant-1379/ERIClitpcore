from litp.core.extension import ModelExtension
from litp.core.model_type import ItemType
from litp.core.model_type import Property
from litp.core.model_type import Collection


class Test12798Extension_test_14(ModelExtension):

    def define_item_types(self):
        return [
            ItemType('parent',
                     extend_item='file-system-base',
                     name=Property("basic_string"),
                     childs=Collection('child'),
                     ),
            ItemType('child',
                     name=Property("basic_string"),
                     grand_children=Collection('g-child'),
                     ),
           ItemType('g-child',
                     extend_item='file-system-base',
                     name=Property("basic_string"),
                     grand_grand_children=Collection('g-g-child'),
                     ),
            ItemType('g-g-child',
                     name=Property("basic_string"),
                     )
        ]
