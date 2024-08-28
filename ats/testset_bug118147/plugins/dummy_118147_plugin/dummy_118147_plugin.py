from litp.core.plugin import Plugin
from litp.core.task import ConfigTask
from litp.core.task import CallbackTask


class Dummy118147Plugin(Plugin):

    def create_configuration(self, api):
        tasks = []
        ms = api.query_by_vpath("/ms")
        device = api.query_by_vpath(
                "/ms/storage_profile/volume_groups/vg1/physical_devices/pd1")
        tasks.append(ConfigTask(
            ms, device, "Fail MS physical device", "foo", "bar"))
        return tasks
