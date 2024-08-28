from litp.core.extension import ModelExtension
from litp.core.model_type import ItemType
from litp.core.model_type import Property


class DummyExtension(ModelExtension):
    def define_item_types(self):
        return [
            ItemType(
                "dummy-package",
                extend_item="software-item",
                name=Property("basic_string", default="foo")
            )
        ]
