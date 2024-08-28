##############################################################################
# COPYRIGHT Ericsson AB 2013
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################

from litp.core.plugin import Plugin
from litp.core.execution_manager import ConfigTask


class FooPackagePlugin(Plugin):
    def create_configuration(self, plugin_api_context):
        tasks = []
        nodes = plugin_api_context.query("node") + \
                plugin_api_context.query("ms")
        for node in nodes:
            for package in node.query("foo-package", is_initial=True):
                task = ConfigTask(node, package, "Description", "package",
                               package.name)
                tasks.append(task)
        for node in nodes:
            for package in node.query("foo-package", is_updated=True):
                task = ConfigTask(node, package, "Update", "package",
                               package.name)
                tasks.append(task)
        for node in nodes:
            for package in node.query("foo-package", is_for_removal=True):
                task = ConfigTask(node, package, "deconfigure", "package",
                               package.name)
                tasks.append(task)
        return tasks
