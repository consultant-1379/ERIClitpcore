from litp.core.extension import ModelExtension
from litp.core.model_type import ItemType
from litp.core.model_type import Property
from litp.core.model_type import Collection


class Test12798Extension(ModelExtension):
    """Mock DHCP Extension """
    def define_item_types(self):
        return [
            ItemType('parent',
                   extend_item='service-base',
                   name=Property("basic_string"),
                   service_name=Property("basic_string"),
                   childs=Collection('child'), # beware of 'children'
            ),
            ItemType('child',
               name=Property("basic_string"),
               service_name=Property("basic_string"),
               grand_children=Collection('grand-child'),
           ),
           ItemType('grand-child',
               name=Property("basic_string"),
               service_name=Property("basic_string"),
           )
        ]

