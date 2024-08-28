from litp.core.extension import ModelExtension
from litp.core.model_type import ItemType
from litp.core.model_type import Property


class DummyExtension(ModelExtension):
    def define_item_types(self):
        return [
             ItemType(
                "dummy_package",
                extend_item="mock-package",
                ro_name=Property(
                    "basic_string",
                    prop_description="Dummy Package Name.",
                    required=True,
                    updatable_plugin=False,
                    updatable_rest=False
                )
            )
        ]
