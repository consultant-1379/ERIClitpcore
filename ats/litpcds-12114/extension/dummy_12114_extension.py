from litp.core.extension import ModelExtension
from litp.core.model_type import ItemType
from litp.core.model_type import Property
from litp.core.model_type import Collection


class Dummy12114Extension(ModelExtension):

    def define_item_types(self):
        return [
            ItemType("package",
                 extend_item="software-item",
                 item_description=("Foo"),
                 name=Property("basic_string",
                     updatable_rest=True,
                     updatable_plugin=True,
                 ),
                 plugin_deps=Property("basic_boolean",
                     default="false"
                 ),
            )
        ]
