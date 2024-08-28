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
from litp.core.model_type import PropertyType
from litp.core.model_type import Collection
from litp.core.validators import ValidationError
from litp.core.validators import ItemValidator

from litp.core.plugin import Plugin
from litp.core.validators import ValidationError
from litp.core.execution_manager import CallbackTask
from litp.core.execution_manager import ConfigTask
from litp.core.task import OrderedTaskList

from litp.core.litp_logging import LitpLogger

import time
import datetime

log = LitpLogger()

#class DummyValidator(ItemValidator):

class TestExtension(ModelExtension):

    def define_item_types(self):
        return [
            ItemType(
                "test-package",
                extend_item="software-item",
                item_description=("This item type represents a "
                                "software package to install."),
                name=Property("basic_string",
                    prop_description="Package name to install/remove.",
                    required=True,
                  ),
             )
        ]

class TestPlugin(Plugin):

    def validate_model(self, plugin_api_context):
        return []

    def callback_method(self, callback_api, *args, **kwargs):
        # do nothing
        pass

    def create_configuration(self, plugin_api_context):
        tasks = []
        node = plugin_api_context.query("ms")[0]
        for package in node.query("test-package", is_initial=True):
            alist = []
            for i in xrange(3):
                alist.append(CallbackTask(
                    package, 
                    "Installing package %s" % package.name,
                    self.callback_method,
                    i))
            tasks.append(OrderedTaskList(package, alist))
        return tasks
