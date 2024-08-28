from litp.core.extension import ModelExtension
from litp.core.model_type import ItemType
from litp.core.model_type import Property, PropertyType


class Dummy11270Extension(ModelExtension):

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
                empty_string_prohibited=Property("basic_string",
                    updatable_rest=True,
                ),
                empty_string_allowed=Property("any_string",
                    updatable_rest=True,
                ),
                item_description=(
                    "The client-side Yum repository configuration."
                ),
            )
        ]
