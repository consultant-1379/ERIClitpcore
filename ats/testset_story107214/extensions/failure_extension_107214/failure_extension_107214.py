from litp.core.extension import ModelExtension
from litp.core.model_type import ItemType
from litp.core.model_type import Property

class FailureExtension(ModelExtension):
    def define_item_types(self):
        return [
            ItemType(
                "litpcds-107214a",
                extend_item="software-item",
                prop=Property("basic_string"),
            ),
            ItemType(
                "litpcds-107214b",
                extend_item="software-item",
                prop=Property("basic_string"),
            )
        ]
