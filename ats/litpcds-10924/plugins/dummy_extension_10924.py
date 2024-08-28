from litp.core.extension import ModelExtension
from litp.core.model_type import ItemType, Property


class DummyExtension10924(ModelExtension):

    def define_item_types(self):

        item_types = []
        item_types.append(
            ItemType('distro-service',
                extend_item='service-base',
                item_description='Stand-in for cobbler',
                name=Property('basic_string', required=True),
            )
        )

        return item_types
