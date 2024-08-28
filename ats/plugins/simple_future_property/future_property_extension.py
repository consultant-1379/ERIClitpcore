from litp.core.extension import ModelExtension
from litp.core.model_type import ItemType
from litp.core.model_type import Property


class FuturePropertyExtension(ModelExtension):
    def define_item_types(self):
        return [
            ItemType(
                "test_item",
                extend_item="software-item",
                name=Property("any_string"),
                version=Property("any_string", updatable_plugin=True),
            ),
        ]
