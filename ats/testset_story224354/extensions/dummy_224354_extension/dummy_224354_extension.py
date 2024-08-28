from litp.core.extension import ModelExtension
from litp.core.model_type import ItemType
from litp.core.model_type import Property


class Dummy224354(ModelExtension):

    def define_item_types(self):
        return [
            ItemType(
                "litpcds-224354",
                extend_item="software-item",
                prop=Property("basic_string"),
            ),
        ]

