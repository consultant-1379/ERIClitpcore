from litp.core.extension import ModelExtension
from litp.core.model_type import ItemType
from litp.core.model_type import Property


class Story4429Extension(ModelExtension):

    def define_item_types(self):

        return [
            ItemType(
                "story4429",
                extend_item="software-item",
                item_description="Item type for LITPCDS-4429",
                name=Property(
                        "basic_string",
                        prop_description="Just a property",
                        required=True,
                    )
                ),
            ItemType(
                "story4429-1",
                extend_item="software-item",
                item_description="Item type for LITPCDS-4429",
                name=Property(
                        "basic_string",
                        prop_description="Just a property",
                        required=True,
                    )
                )
            ]
