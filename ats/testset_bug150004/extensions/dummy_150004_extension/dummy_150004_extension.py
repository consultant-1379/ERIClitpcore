from litp.core.extension import ModelExtension
from litp.core.model_type import ItemType
from litp.core.model_type import Property
from litp.core.model_type import Collection


class Dummy150004Extension(ModelExtension):

    def define_item_types(self):
        return [
            ItemType('parent',
                   extend_item='service-base',
                   name=Property("basic_string"),
                   childs=Collection('child'),
            ),
            ItemType('child',
               name=Property("basic_string"),
           ),
        ]

