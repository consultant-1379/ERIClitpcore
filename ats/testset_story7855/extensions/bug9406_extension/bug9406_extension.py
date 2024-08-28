from litp.core.extension import ModelExtension
from litp.core.model_type import ItemType
from litp.core.model_type import Property
from litp.core.model_type import Child
from litp.core.model_type import Reference
from litp.core.model_type import RefCollection


class DummyExtension(ModelExtension):
    def define_item_types(self):
        return [
            ItemType(
                "container",
                extend_item="profile",
                child=Child("child-item"),
                ref=Reference("storage-profile-base"),
                name=Property("basic_string", updatable_plugin=True),
                hostname=Property("basic_string", updatable_plugin=True),
                ),
            ItemType(
                "child-item",
                name=Property("basic_string", updatable_plugin=True),
                hostname=Property("basic_string", updatable_plugin=True),
                container_two=Child("container")
            )

        ]
