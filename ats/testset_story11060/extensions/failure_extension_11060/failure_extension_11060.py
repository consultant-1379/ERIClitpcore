from litp.core.extension import ModelExtension
from litp.core.model_type import ItemType
from litp.core.model_type import Property
from litp.core.model_type import Child
from litp.core.model_type import Reference
from litp.core.model_type import RefCollection


class FailureExtension(ModelExtension):
    def define_item_types(self):
        return [
            ItemType(
                "litpcds-11060a",
                extend_item="software-item",
                prop=Property("basic_string"),
            ),
            ItemType(
                "litpcds-11060b",
                extend_item="software-item",
                prop=Property("basic_string"),
            )
        ]
