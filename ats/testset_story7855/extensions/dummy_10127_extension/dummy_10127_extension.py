from litp.core.extension import ModelExtension
from litp.core.model_type import ItemType
from litp.core.model_type import Property
from litp.core.model_type import Child
from litp.core.model_type import Reference
from litp.core.model_type import RefCollection


class Dummy10127Extension(ModelExtension):
    def define_item_types(self):
        return [
            ItemType(
                "litpcds-10127",
                extend_item="profile",
                name=Property("basic_string", updatable_plugin=True),
                hostname=Property("basic_string", updatable_plugin=True),
                ),
        ]
