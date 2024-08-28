from litp.core.extension import ModelExtension
from litp.core.model_type import ItemType
from litp.core.model_type import Property
from litp.core.model_type import Collection


class Dummy12781Extension(ModelExtension):

    def define_item_types(self):
        return [
            ItemType('test_12781_tc01',
               extend_item='service-base',
               name=Property("basic_string"),
            ),
            ItemType('test_12781_tc02',
               extend_item='service-base',
               name=Property("basic_string"),
            ),
            ItemType('test_12781_tc03',
               extend_item='service-base',
               name=Property("basic_string"),
            ),
            ItemType('test_12781_tc04',
               extend_item='service-base',
               name=Property("basic_string"),
            ),
            ItemType('test_12781_tc06',
               extend_item='service-base',
               name=Property("basic_string"),
            ),
            ItemType('test_12781_tc07',
               extend_item='service-base',
               name=Property("basic_string"),
            ),
            ItemType('test_12781_tc08',
               extend_item='service-base',
               name=Property("basic_string"),
            ),
            ItemType('test_12781_tc09',
               extend_item='service-base',
               name=Property("basic_string"),
            ),
            ItemType('test_12781_tc10',
               extend_item='service-base',
               name=Property("basic_string"),
            ),
            ItemType('test_12781_tc11',
               extend_item='service-base',
               name=Property("basic_string"),
            )
        ]
