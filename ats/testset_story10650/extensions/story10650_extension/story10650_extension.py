from litp.core.extension import ModelExtension
from litp.core.model_type import ItemType, Property


class Story10650Extension(ModelExtension):

    def define_item_types(self):
        return [
            ItemType(
                'story10650',
                extend_item='software-item',
                name=Property('basic_string')
            ),
            ItemType(
                'depend10650',
                extend_item='software-item',
                name=Property('basic_string')
            )
        ]
