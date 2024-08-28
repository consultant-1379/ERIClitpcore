from litp.core.extension import ModelExtension
from litp.core.model_type import ItemType, Property, PropertyType


class Story5649Extension(ModelExtension):

    def define_property_types(self):
        return [
            PropertyType(
                'task_number',
                regex='^(one|many)$'
                )
            ]

    def define_item_types(self):
        return [
            ItemType(
                'story5649',
                extend_item='software-item',
                name=Property('basic_string'),
                extra_items=Property('any_string'),
                number_of_tasks=Property('task_number')
            ),
        ]
