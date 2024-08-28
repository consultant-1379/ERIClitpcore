from litp.core.extension import ModelExtension
from litp.core.model_type import ItemType
from litp.core.model_type import Property
from litp.core.model_type import Collection


class DummyInheritExtension(ModelExtension):
    def define_item_types(self):
        return [
            ItemType(
                "storage-profile",
                extend_item="storage-profile-base",
                description=Property("basic_string"),
                filesystems=Collection("fs"),
                name=Property("basic_string"),
                number=Property("basic_string", default="42"),
            ),
            ItemType(
                "fs",
                name=Property("basic_string", required=True),
                size=Property("basic_string", default="0"),
                description=Property("basic_string")
            )
        ]
