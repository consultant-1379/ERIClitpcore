from litp.core.extension import ModelExtension
from litp.core.model_type import ItemType
from litp.core.model_type import Property
from litp.core.model_type import Child
from litp.core.model_type import Reference
from litp.core.model_type import Collection
from litp.core.model_type import RefCollection


class DummyExtensionPackage(ModelExtension):
    def define_item_types(self):
        return [
            ItemType(
                "foo",
                extend_item="software-item",
                name=Property("any_string"),

                c=Child("system"),
                r=Reference("system"),

                ccitems=Collection("system"),
                rcitems=RefCollection("system"),
            ),
        ]
