from litp.core.extension import ModelExtension
from litp.core.model_type import ItemType
from litp.core.model_type import Property
from litp.core.model_type import Collection

class UpdateSrcPropExtension(ModelExtension):
    """
    Updatable plugin Extension
    """

    def define_item_types(self):
        return [
            ItemType(
                "dummy-package",
                         extend_item="software-item",
                         item_description=("This item type represents "
                                        "a software package to install."),
                         name=Property("basic_string",
                                        prop_description="Package name to "
                                                         "install/remove.",
                                       required=True,
                                       ),
                         updatable=Property("any_string",
                                    prop_description="Updatable property",
                                    updatable_rest=True,
                                    updatable_plugin=True
                                    ),
                    ),
            ItemType(
                "myrepository",
                extend_item="software-item",
                name=Property(
                    "basic_string",
                    prop_description="my Repository Name.",
                    required=True,
                    updatable_plugin=False,
                    updatable_rest=False
                ),
                myprop1=Property(
                    "basic_string",
                    prop_description="My first property description",
                    updatable_plugin=True,
                    updatable_rest=True,
                ),
                myprop2=Property(
                    "basic_string",
                    prop_description="My second property description",
                    updatable_plugin=True,
                    updatable_rest=True,
                ),
                packages=Collection(
                    "dummy-package"
                ),
                item_description=(
                    "my repository configuration."
                ),
            )
        ]
