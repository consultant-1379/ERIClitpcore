from litp.core.extension import ModelExtension
from litp.core.model_type import ItemType, Property


class Story10575Extension(ModelExtension):

    def define_item_types(self):
        return [
            ItemType(
                'story10575',
                extend_item='software-item',
                name=Property('basic_string'),
                config=Property('basic_boolean'),
                deconfig=Property('basic_boolean')
            )
        ]
