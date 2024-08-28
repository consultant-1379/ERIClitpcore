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
from litp.core.exceptions import PluginError

class UpdateModelErrorPlugin(Plugin):
    """
    LITP Mock volmgr plugin to provide snapshots tasks in ats
    """

    def __init__(self, *args, **kwargs):
        super(UpdateModelErrorPlugin, self).__init__(*args, **kwargs)

    def update_model(self, plugin_api_context):
        raise PluginError(
            'Not all yum-repository checksums can be updated')
