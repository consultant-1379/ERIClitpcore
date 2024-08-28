from litp.core.extension import ModelExtension
from litp.core.model_type import ItemType
from litp.core.model_type import Property


class DummyBarExtension(ModelExtension):
    def define_item_types(self):
        return [
            ItemType(
                "bar",
                extend_item="software-item",
                name=Property("any_string")
            ),
        ]
