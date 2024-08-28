from litp.core.extension import ModelExtension
from litp.core.model_type import ItemType
from litp.core.model_type import Property
from litp.core.model_type import Collection
from litp.core.model_type import RefCollection
from litp.core.model_type import Reference


class Invalid13008Extension(ModelExtension):
    def define_item_types(self):
        return [
            ItemType('parent',
                   extend_item='service-base',
                   source=Property("basic_string"),
                   children=Collection('child'),
                   vpath=RefCollection('child'),
            ),
            ItemType('child',
               name=Property("basic_string"),
           ),
        ]

