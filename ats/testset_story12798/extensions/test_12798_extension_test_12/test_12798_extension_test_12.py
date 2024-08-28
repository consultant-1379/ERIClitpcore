from litp.core.extension import ModelExtension
from litp.core.model_type import ItemType
from litp.core.model_type import Property
from litp.core.model_type import Collection


class Test12798Extension_test_12(ModelExtension):

    def define_item_types(self):
        return [
            ItemType('parent',
                     extend_item='software-item',
                     name=Property("basic_string"),
                     childs=Collection('child'),  # beware of 'children'
                     ),
            ItemType('child',
                     extend_item='software-item',
                     name=Property("basic_string"),
                     grand_children=Collection('g-child'),
                     ),
            ItemType('g-child',
                     name=Property("basic_string"),
                     extend_item='software-item',
                     grand_grand_children=Collection('g-g-child'),
                     ),
            ItemType('g-g-child',
                     extend_item='software-item',
                     name=Property("basic_string")
                     ),
            ItemType('parent-b',
                     extend_item='service',
                     name=Property("basic_string"),
                     )
        ]
