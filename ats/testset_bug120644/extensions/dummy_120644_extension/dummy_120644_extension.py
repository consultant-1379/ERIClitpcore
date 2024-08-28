from litp.core.extension import ModelExtension
from litp.core.model_type import ItemType
from litp.core.model_type import Property
from litp.core.model_type import Child


class Dummy120644Extension(ModelExtension):

    def define_item_types(self):
        return [
            ItemType('vm-service',
                extend_item='service',
                foo=Child('child_type_a', required=True),
                bar=Child('child_type_b', required=True),
                baz=Child('child_type_c', required=True),
                quux=Child('child_type_d', required=True),
            ),
            ItemType('child_type_a',
                name=Property("basic_string"),
            ),
            ItemType('child_type_b',
                name=Property("basic_string"),
            ),
            ItemType('child_type_c',
                name=Property("basic_string"),
            ),
            ItemType('child_type_d',
                name=Property("basic_string"),
            ),
        ]

