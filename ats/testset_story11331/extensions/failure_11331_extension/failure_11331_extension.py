from litp.core.extension import ModelExtension
from litp.core.model_type import ItemType
from litp.core.model_type import Property, PropertyType
from litp.core.model_type import Collection
from litp.core.model_type import Reference

class Failure11331Extension(ModelExtension):

    def define_item_types(self):
        return [
           ItemType(
                'foo',
                extend_item='software-item',
                name=Property('basic_string'),
            ),
           ItemType(
                'bar',
                extend_item='software-item',
                name=Property('basic_string'),
                ref_read_only=Reference("yum-repository", read_only=True),
            ),
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
                required_prop2=Property("basic_string",
                    required=True,
                    updatable_plugin=True,
                    updatable_rest=True,
                ),
                not_updatable_prop=Property("basic_string",
                    updatable_plugin=False,
                    updatable_rest=False,
                ),
                not_a_property=Collection("foo"),
                item_description=(
                    "The client-side Yum repository configuration."
                ),
            )
        ]
