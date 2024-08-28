from litp.core.plugin import Plugin
from litp.core.task import ConfigTask
from litp.core.task import CallbackTask

from litp.core.litp_logging import LitpLogger
log = LitpLogger()


class Story7721Plugin(Plugin):
    def create_configuration(self, api):
        """
        Plan1:
            Create ConfigTask1(pkg), CallbackTask1(pkg), ConfigTask3(eth)
            Task-to-task dependencies:
                CallbackTask1(pkg) -> ConfigTask1(pkg)
                ConfigTask2(eth) -> CallbackTask1(pkg)
        Plan2:
            Create ConfigTask3(srv)
            Recreate CallbackTask1(pkg)
            Model dependencies (ConfigTask2 from Plan 1):
                ConfigTask3(srv) -> ConfigTask2(eth)
        """
        ms = api.query('ms')[0]
        tasks = []
        pkg = ms.query('software-item')[0]
        if ms.is_initial():
            eth = ms.query('network-interface')[0]
            cfg1 = ConfigTask(ms, pkg, "Plugin1 ConfigTask1", "package",
                              "test5")
            cb1 = CallbackTask(pkg, "Plugin1 CallbackTask1", self._callback)
            cfg2 = ConfigTask(ms, eth, "Plugin1 ConfigTask2", "eth", "test5")
            cfg2.requires.add(cb1)
            cb1.requires.add(cfg1)
            tasks = [cfg1, cb1, cfg2]
        else:
            srv = ms.query('service-base')[0]
            cb1 = CallbackTask(pkg, "Plugin1 CallbackTask1", self._callback)
            # service will require network interface (model sibling dependency)
            cfg3 = ConfigTask(ms, srv, "Plugin1 ConfigTask3", "service",
                              "test5")
            tasks = [cb1, cfg3]

        return tasks

    def _callback(self, *args):
        pass
