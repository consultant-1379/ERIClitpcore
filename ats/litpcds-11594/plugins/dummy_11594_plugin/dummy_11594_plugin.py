from litp.core.plugin import Plugin
from litp.core.task import ConfigTask
from litp.core.task import CallbackTask
import hashlib


class Dummy11594Plugin(Plugin):

    def create_configuration(self, api):
        tasks = []
        for node in api.query("node"):
            for yum_repo in node.query("yum-repository"):
                tasks.append(CallbackTask(yum_repo, "Dummy callback "
                    "task for {0}".format(yum_repo.name), self._dummy_cb))
        return tasks

    def _dummy_cb(self, api):
        pass

    def update_model(self, plugin_api_context):
        # Only update source (ref items don't return here)
        for yum_repo in plugin_api_context.query("yum-repository"):
            if yum_repo.get_state() not in ('Initial'):
                if not yum_repo.checksum:
                    # Set the checksum property
                    md5sum = hashlib.md5('dummy_value').hexdigest()
                    yum_repo.checksum = md5sum
                else:
                    # Try to unset the checksum
                    yum_repo.clear_property('checksum')
