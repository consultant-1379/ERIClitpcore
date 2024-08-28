
from litp.core.extension import ModelExtension
from litp.core.model_type import ItemType
from litp.core.model_type import Property
from litp.core.model_type import Collection


class DummyExtension10798(ModelExtension):
    """
    LITP Mock package extension for testing.
    """

    def define_item_types(self):
        return [
            ItemType(
                "re-mock-package",
                         extend_item="software-item",
                         item_description=("This item type represents "
                                        "a software package to install."),
                         name=Property("basic_string",
                                        prop_description="Package name to "
                                                         "install/remove.",
                                       required=True,
                                       ),
                         version=Property("any_string",
                                           prop_description="Package version "
                                                       "to install/remove.",
                                           ),
                         release=Property("any_string",
                                          prop_description="Package release "
                                                         "to install/remove.",
                                            ),
                         arch=Property("any_string",
                                       prop_description="Package arch to "
                                                        "install/remove.",
                                        ),
                         ensure=Property("any_string",
                                    prop_description="Constraint for package "
                                                     "enforcement.",
                                    default="installed",
                                   ),
                         config=Property("any_string",
                                    prop_description="Constraint for "
                                                 "configuration retention.",
                                    ),
                         repository=Property("any_string",
                                    prop_description="Name of repository "
                                                         "to get Package.",
                                        ),
                    )
                ]
