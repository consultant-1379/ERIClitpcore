from litp.core.extension import ModelExtension
from litp.core.model_type import ItemType
from litp.core.model_type import Property


class Dummy7855Extension(ModelExtension):
    def define_item_types(self):
        return [
            ItemType(
                "bar",
                extend_item="software-item",
                name=Property("any_string")
            ),
            ItemType(
                "baz",
                extend_item="software-item",
                name=Property("any_string")
            ),
            ItemType(
                "foo",
                extend_item="software-item",
                name=Property("any_string")
            ),
        ]
