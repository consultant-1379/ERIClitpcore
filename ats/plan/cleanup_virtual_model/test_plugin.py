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
from litp.core.execution_manager import ConfigTask

from litp.core.litp_logging import LitpLogger

from itertools import count

import time
import datetime

log = LitpLogger()
id_counter = count()

class TestPlugin(Plugin):

    def validate_model(self, plugin_api_context):
        return []

    def create_configuration(self, plugin_api_context):
        tasks = []
        nodes = []
        nodes += plugin_api_context.query('ms')
        nodes += plugin_api_context.query('node')
        for node in nodes:
            for disk in node.query("disk", is_initial=True):
                tasks.append(ConfigTask(
                    node, disk,
                    "Installing system disk %s" % disk.name,
                    'disk',
                    'disk-%d' % id_counter.next()
                    ))
        return tasks
