from litp.core.extension import ModelExtension
from litp.core.model_type import ItemType
from litp.core.model_type import Property
from litp.core.model_type import View
from litp.core.exceptions import ViewError

class Dummy10675Extension(ModelExtension):
    def define_item_types(self):
        return [
            ItemType(
                "deprecation",
                extend_item="software-item",
                deprecated_property=Property(
                    "basic_string",
                    default='mayfly',
                    deprecated=True
                ),
            ),
        ]
