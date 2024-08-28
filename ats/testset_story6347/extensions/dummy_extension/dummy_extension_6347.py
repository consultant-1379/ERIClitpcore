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
                "dummy-profile",
                extend_item="profile",
                item=Child("dummy-item"),
                ro=Child("dummy-ro", required=True),
                rw=Child("dummy-rw", required=True)
            ),
            ItemType(
                "dummy-item",
                name=Property("basic_string", updatable_plugin=True),
                item=Child("dummy-item")
            ),
            ItemType(
                "dummy-rw",
                ref=Reference("dummy-item"),
                refcoll=RefCollection("dummy-item")
            ),
            ItemType(
                "dummy-ro",
                ref=Reference("dummy-item", read_only=True),
                refcoll=RefCollection("dummy-item", read_only=True)
            )
        ]
