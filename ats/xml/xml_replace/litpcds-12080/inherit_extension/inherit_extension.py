from litp.core.extension import ModelExtension
from litp.core.model_type import ItemType
from litp.core.model_type import Property
from litp.core.model_type import Child
from litp.core.model_type import Reference
from litp.core.model_type import RefCollection


class InheritExtension(ModelExtension):
    def define_item_types(self):
        return [
            ItemType(
                "inherit_extension",
                extend_item="mock-package",
            )
        ]
