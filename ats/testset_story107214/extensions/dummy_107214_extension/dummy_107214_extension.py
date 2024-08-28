from litp.core.extension import ModelExtension
from litp.core.model_type import ItemType
from litp.core.model_type import Property


class Dummy107214Extension(ModelExtension):

    def define_item_types(self):
        return [
            ItemType(
                "litpcds-107214",
                extend_item="software-item",
                prop=Property("basic_string"),
            ),
        ]

