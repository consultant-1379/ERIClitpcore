from litp.core.extension import ModelExtension
from litp.core.model_type import ItemType
from litp.core.model_type import Property
from litp.core.model_type import Collection


class Mixedstates12018Extension(ModelExtension):
    """Mock Story12018 Extension """
    def define_item_types(self):
        return [
            ItemType('parent1',
                   extend_item='service-base',
                   name=Property("basic_string"),
                   childs=Collection('child1'),
            ),
            ItemType('child1',
               name=Property("basic_string"),
               grand_children=Collection('grand-child1'),
           ),
           ItemType('grand-child1',
               name=Property("basic_string"),
           )
        ]

