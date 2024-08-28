from litp.core.extension import ModelExtension
from litp.core.model_type import ItemType
from litp.core.model_type import Property


class Story7721Extension(ModelExtension):

    def define_item_types(self):
        return [
            ItemType(
                "story-7721a",
                extend_item="node-config",
                name=Property("any_string"),
                deconfigure=Property("any_string", default="false")
            ),
            ItemType(
                "story-7721b",
                extend_item="node-config",
                name=Property("any_string"),
            ),
            ItemType(
                "depend-story-7721",
                extend_item="software-item",
                name=Property("any_string"),
            )
        ]
