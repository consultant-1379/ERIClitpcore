from litp.core.extension import ModelExtension
from litp.core.model_type import ItemType
from litp.core.model_type import Property
from litp.core.model_type import Collection


class Dummy194416Extension(ModelExtension):

    def define_item_types(self):
        return [
            ItemType('trigger-194416',
                   extend_item='software-item',
                   behaviour=Property("basic_string"),
            ),
        ]

