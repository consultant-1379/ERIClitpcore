from litp.core.extension import ModelExtension
from litp.core.model_type import ItemType
from litp.core.model_type import Property
from litp.core.model_type import Collection


class Dummy200086Extension(ModelExtension):

    def define_item_types(self):
        return [
            ItemType('parent',
                   extend_item='software-item',
                   name=Property("basic_string"),
                   childs=Collection('child'),
            ),
            ItemType('child',
               name=Property("basic_string"),
           ),
        ]

