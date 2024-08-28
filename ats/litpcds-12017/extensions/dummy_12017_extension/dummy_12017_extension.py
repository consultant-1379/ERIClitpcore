from litp.core.extension import ModelExtension
from litp.core.model_type import ItemType
from litp.core.model_type import Property
from litp.core.model_type import Collection


class Dummy12017Extension(ModelExtension):

    def define_item_types(self):
        # LITPCDS-12017: Remove in plan parent, but fail plan before child
        # item is removed during cleanup at end of plan
        return [
            ItemType("dummy-12017",
                 extend_item="mock-package",
                 packages=Collection("dummy-12017"),
                 item_description=("This item type has a packages "
                     "CollectionItem to replicate LITPCDS-12017"),
                 updatable_prop=Property("basic_string",
                     updatable_rest=True,
                     updatable_plugin=True,
                 )
            )
        ]
