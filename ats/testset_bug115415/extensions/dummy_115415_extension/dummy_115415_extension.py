from litp.core.extension import ModelExtension
from litp.core.model_type import ItemType
from litp.core.model_type import Property
from litp.core.model_type import Collection


class Dummy115415Extension(ModelExtension):

    def define_item_types(self):
        return [
            ItemType('trigger',
                extend_item='software-item',
                name=Property("basic_string", required=True),
            ),
        ]
