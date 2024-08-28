
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
from litp.core.execution_manager import ConfigTask, CallbackTask

from litp.core.litp_logging import LitpLogger

log = LitpLogger()


class TestPlugin(Plugin):

    def _callback(self):
        pass

    def create_configuration(self, plugin_api_context):

        ms = plugin_api_context.query('ms')[0]
        pkg = ms.query("mock-package")[0]
        net = ms.query("network-interface")[0]
        pkg_task = ConfigTask(ms, pkg, "Installing package",
                              'package', 'package-1', param=1)
        net_task = ConfigTask(ms, net, "Setting up iface",
                              'iface', 'iface-1', param=ms.is_initial())
        pkg_task.requires.add(net)

        return [pkg_task, net_task]
