
from litp.core.plugin import Plugin
from litp.core.extension import ModelExtension

from litp.core.validators import ValidationError
from litp.core.execution_manager import CallbackTask
from litp.core.execution_manager import ConfigTask
from litp.core.task import OrderedTaskList
from litp.core.model_type import ItemType
from litp.core.model_type import Property
from litp.core.model_type import Collection

from litp.core.litp_logging import LitpLogger

import time
import datetime

log = LitpLogger()


class XmlExtension(ModelExtension):
    def define_item_types(self):
        return [
            ItemType(
                "mock-software-entity",
                extend_item="software-item",
                item_description=("This item type represents a "
                                "software package to install."),
                name=Property("basic_string",
                    prop_description="Entity name.",
                ),
                packages=Collection("mock-item"),
            ),
            ItemType(
                "mock-item",
                name=Property("basic_string"),
            ),
            ItemType(
                "mock-item-extension",
                extend_item="mock-item",
                version=Property("basic_string"),
            ),
        ]

#class XmlPlugin(Plugin):
#    def create_configuration(self, plugin_api_context):
#        tasks = []
#        return tasks
