from litp.core.extension import ModelExtension
from litp.core.model_type import ItemType, Property, PropertyType


class Story10531Extension(ModelExtension):

    def define_property_types(self):
        return [
            PropertyType('task_dependency', regex='^(ingroup|outgroup|t2t|call_type_id|query_item)$')
        ]

    def define_item_types(self):
        return [
            ItemType(
                'foo1',
                extend_item='software-item',
                name=Property('basic_string'),
            ),
            ItemType(
                'foo2_1',
                extend_item='software-item',
                name=Property('basic_string'),
            ),
            ItemType(
                'foo2_2',
                extend_item='software-item',
                name=Property('basic_string'),
            ),
            ItemType(
                'foo2_3',
                extend_item='software-item',
                name=Property('basic_string'),
            ),
            ItemType(
                'foo3',
                extend_item='software-item',
                name=Property('basic_string'),
            ),
            ItemType(
                'foo4',
                extend_item='software-item',
                name=Property('basic_string'),
                task_dependency_type=Property('task_dependency')
            ),
            ItemType(
                'foo5',
                extend_item='software-item',
                name=Property('basic_string'),
            ),
            ItemType(
                'foo6',
                extend_item='software-item',
                name=Property('basic_string'),
                task_dependency_type=Property('task_dependency')
            ),
            ItemType(
                'foo7',
                extend_item='software-item',
                name=Property('basic_string'),
            ),
            ItemType(
                'foo8',
                extend_item='software-item',
                name=Property('basic_string'),
            ),
        ]
