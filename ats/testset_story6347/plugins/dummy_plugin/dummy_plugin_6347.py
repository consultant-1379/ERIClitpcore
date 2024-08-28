from litp.core.plugin import Plugin
from litp.core.task import CallbackTask


class DummyPlugin(Plugin):
    def _cb(self, api, *args, **kwargs):
        for dummy_profile in api.query("dummy-profile"):
            for dummy_item in dummy_profile.query("dummy-item"):
                if dummy_item.vpath == "/software/profiles/dummy/ro/ref":
                    # this is the only item we are interested in
                    dummy_item.name = "bar"

    def create_configuration(self, api):
        tasks = []
        for dummy_profile in api.query("dummy-profile"):
            for dummy_item in dummy_profile.query("dummy-item"):
                if dummy_item.vpath == "/software/profiles/dummy/ro/ref":
                    # this is the only item we are interested in
                    tasks.append(
                        CallbackTask(dummy_item, "", self._cb)
                    )
        return tasks

