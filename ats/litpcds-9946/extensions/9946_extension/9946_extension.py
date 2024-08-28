from litp.core.extension import ModelExtension
from litp.core.model_type import ItemType
from litp.core.model_type import Property


class Extension_9946(ModelExtension):
    def define_item_types(self):
        return [
            ItemType(
                "mysql-server",
                extend_item="service",
                name=Property("any_string"),
                custom_name=Property("any_string")
            )
        ]
