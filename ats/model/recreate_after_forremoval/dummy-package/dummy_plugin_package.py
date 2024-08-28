from litp.core.plugin import Plugin
from litp.core.task import ConfigTask


class DummyPluginPackage(Plugin):
    def create_configuration(self, api):
        tasks = []
        ms = api.query("ms")[0]
        for foo in api.query("foo"):
            if foo.is_initial() or foo.is_updated() or foo.is_for_removal():
                tasks.append(
                    ConfigTask(ms, foo, foo.get_state(), "foo", foo.name)
                )
        return tasks
