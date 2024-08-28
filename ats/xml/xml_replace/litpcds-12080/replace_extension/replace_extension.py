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
                "dummy_extension",
                extend_item="node-config",
                property1=Property(
                    "basic_string",
                    prop_description="TRUE TRUE TRUE TRUE",
                    required=True,
                    updatable_plugin=True,
                    updatable_rest=True,
                    default="this_is_a_default_value"
                ),
                property2=Property(
                    "basic_string",
                    prop_description="TRUE FALSE TRUE TRUE",
                    required=True,
                    updatable_plugin=True,
                    updatable_rest=False,
                    default="this_is_a_default_value"
                ),
                property3=Property(
                    "basic_string",
                    prop_description="FALSE TRUE TRUE TRUE",
                    required=True,
                    updatable_plugin=False,
                    updatable_rest=True,
                    default="this_is_a_default_value"
                ),
                property4=Property(
                    "basic_string",
                    prop_description="FALSE FALSE TRUE TRUE",
                    required=True,
                    updatable_plugin=False,
                    updatable_rest=False,
                    default="this_is_a_default_value"
                ),

                property5=Property(
                    "basic_string",
                    prop_description="TRUE TRUE TRUE FALSE",
                    required=True,
                    updatable_plugin=True,
                    updatable_rest=True,
                ),
                property6=Property(
                    "basic_string",
                    prop_description="TRUE FALSE TRUE FALSE",
                    required=True,
                    updatable_plugin=True,
                    updatable_rest=False,
                ),
                property7=Property(
                    "basic_string",
                    prop_description="FALSE TRUE TRUE FALSE",
                    required=True,
                    updatable_plugin=False,
                    updatable_rest=True,
                ),
                property8=Property(
                    "basic_string",
                    prop_description="FALSE FALSE TRUE FALSE",
                    required=True,
                    updatable_plugin=False,
                    updatable_rest=False,
                ),

                property9=Property(
                    "basic_string",
                    prop_description="TRUE TRUE FALSE TRUE",
                    required=False,
                    updatable_plugin=True,
                    updatable_rest=True,
                    default="this_is_a_default_value"
                ),
                property10=Property(
                    "basic_string",
                    prop_description="TRUE FALSE FALSE TRUE",
                    required=False,
                    updatable_plugin=True,
                    updatable_rest=False,
                    default="this_is_a_default_value"
                ),
                property11=Property(
                    "basic_string",
                    prop_description="FALSE TRUE FALSE TRUE",
                    required=False,
                    updatable_plugin=False,
                    updatable_rest=True,
                    default="this_is_a_default_value"
                ),
                property12=Property(
                    "basic_string",
                    prop_description="FALSE FALSE FALSE TRUE",
                    required=False,
                    updatable_plugin=False,
                    updatable_rest=False,
                    default="this_is_a_default_value"
                ),

                property13=Property(
                    "basic_string",
                    prop_description="TRUE TRUE FALSE FALSE",
                    required=False,
                    updatable_plugin=True,
                    updatable_rest=True,
                ),
                property14=Property(
                    "basic_string",
                    prop_description="TRUE FALSE FALSE FALSE",
                    required=False,
                    updatable_plugin=True,
                    updatable_rest=False,
                ),
                property15=Property(
                    "basic_string",
                    prop_description="FALSE TRUE FALSE FALSE",
                    required=False,
                    updatable_plugin=False,
                    updatable_rest=True,
                ),
                property16=Property(
                    "basic_string",
                    prop_description="FALSE FALSE FALSE FALSE",
                    required=False,
                    updatable_plugin=False,
                    updatable_rest=False,
                ),
            )
        ]
