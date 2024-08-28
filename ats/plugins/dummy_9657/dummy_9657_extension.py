from litp.core.extension import ModelExtension
from litp.core.model_type import ItemType
from litp.core.model_type import Property


class Dummy9657Extension(ModelExtension):
    def define_item_types(self):
        return [
            ItemType(
                "foo",
                extend_item="software-item",
                name=Property("any_string")
            ),
            ItemType(
                "boot-service",
                extend_item="service-base",
                name=Property("basic_string")
            )
        ]
