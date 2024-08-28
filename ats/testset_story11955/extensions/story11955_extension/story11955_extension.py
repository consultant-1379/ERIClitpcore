from litp.core.extension import ModelExtension
from litp.core.model_type import ItemType, Property


class Story11955Extension(ModelExtension):

    def define_item_types(self):
        return [
            ItemType(
                'story11955',
                extend_item='software-item',
                name=Property('basic_string'),
                testcase=Property('basic_string'),
            )
        ]
