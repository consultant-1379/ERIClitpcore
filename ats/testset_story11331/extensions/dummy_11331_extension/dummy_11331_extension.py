from litp.core.extension import ModelExtension
from litp.core.model_type import ItemType
from litp.core.model_type import Property, PropertyType


class Dummy11331Extension(ModelExtension):

    def define_item_types(self):
        return [
            ItemType(
                "yum-repository",
                extend_item="software-item",
                name=Property(
                    "basic_string",
                    prop_description="Yum Repository Name.",
                    required=True,
                    updatable_plugin=False,
                    updatable_rest=False
                ),
                checksum=Property(
                    "checksum_hex_string",
                    prop_description="Checksum for yum repository",
                    updatable_plugin=True,
                    updatable_rest=False,
                ),
                optional_prop=Property("basic_string",
                    updatable_plugin=True,
                    updatable_rest=True,
                ),
                optional_prop1=Property("basic_string",
                    updatable_plugin=True,
                    updatable_rest=True,
                ),
                optional_prop2=Property("basic_string",
                    updatable_plugin=True,
                    updatable_rest=False,
                ),
                required_prop1=Property("basic_string",
                    required=True,
                    updatable_plugin=True,
                    updatable_rest=True,
                    default="story11331"
                ),
                ac1_prop=Property("basic_string",
                    required=False,
                    updatable_plugin=True,
                    updatable_rest=True,
                    site_specific=False,
                    deprecated=False
                ),
                ac2_prop=Property("basic_string",
                    required=True,
                    updatable_plugin=True,
                    updatable_rest=True,
                    default="story11331_ac2",
                    site_specific=False,
                    deprecated=False
                ),
                ac3_prop=Property("basic_string",
                    required=False,
                    updatable_plugin=True,
                    updatable_rest=True,
                    site_specific=False,
                    deprecated=False
                ),
                ac6_prop=Property("basic_string",
                    required=False,
                    updatable_plugin=True,
                    updatable_rest=True,
                    site_specific=False,
                    deprecated=False
                ),
                ac7_prop=Property("basic_string",
                    required=False,
                    updatable_plugin=True,
                    updatable_rest=True,
                    site_specific=False,
                    deprecated=False
                ),
                ac9_prop=Property("basic_string",
                    required=True,
                    updatable_plugin=True,
                    updatable_rest=True,
                    site_specific=False,
                    deprecated=False
                ),
                item_description=(
                    "The client-side Yum repository configuration."
                ),
            )
        ]
