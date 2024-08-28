from litp.core.extension import ModelExtension
from litp.core.model_type import ItemType
from litp.core.model_type import Property
from litp.core.model_type import Collection


class Dummy111759Extension(ModelExtension):

    def define_item_types(self):
        return [
            ItemType('three_children',
                extend_item='software-item',
                name=Property("basic_string", required=True),
                middle=Collection("software-item"),
            ),
            ItemType('left-first',
                extend_item='three_children',
                left=Collection("software-item"),
                right=Collection("software-item", require="left"),
            ),
            ItemType('right-first',
                extend_item='three_children',
                left=Collection("software-item", require="right"),
                right=Collection("software-item"),
            ),
        ]
