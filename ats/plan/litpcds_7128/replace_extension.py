##############################################################################
# COPYRIGHT Ericsson AB 2013
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################


from litp.core.extension import ModelExtension
from litp.core.model_type import ItemType
from litp.core.model_type import Property
from litp.core.model_type import Collection


class ReplaceExtension(ModelExtension):
    """
    LITP Mock package extension for testing.
    """

    def define_item_types(self):
        return [
            ItemType(
                "replaceable",
                         extend_item="software-item",
                         item_description="fooo",
                         name=Property("basic_string",
                                        prop_description="Package name to "
                                                         "install/remove.",
                                       required=True,
                                       ),
                         drop_all=Property("any_string",
                                           prop_description="Package version "
                                                           "to install/remove.",
                                           ),
                    )
                ]

