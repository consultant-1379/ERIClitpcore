from litp.core.extension import ModelExtension
from litp.core.model_type import ItemType
from litp.core.model_type import Property


class FooPackageExtension(ModelExtension):
    def define_item_types(self):
        return [
            ItemType(
                "foo-package",
                extend_item="software-item",
                name=Property("any_string")
            ),
        ]
