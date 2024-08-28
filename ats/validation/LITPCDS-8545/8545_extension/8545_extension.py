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
                "yum-repository",
                extend_item="mock-package",
                ro_name=Property(
                    "basic_string",
                    prop_description="Yum Repository Name.",
                    required=True,
                    updatable_plugin=False,
                    updatable_rest=False
                )
            )
        ]
