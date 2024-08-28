from litp.core.plugin import Plugin
from litp.core.task import ConfigTask
from litp.core.task import CallbackTask

from litp.core.litp_logging import LitpLogger
log = LitpLogger()


class Story7721Plugin(Plugin):
    def create_configuration(self, api):
        """
        Plan 1:
            Create ConfigTask1(package), ConfigTask2(service),
                CallbackTask1(package)
            Model dependencies:
                None
            QueryItem dependencies:
                ms.system:
                ConfigTask1(package) -> * /not resolved to anything/
            Call type + call id dependencies:
                (config, test6)
                ConfigTask2(service) -> *

        Plan 2:
            Create ConfigTask3(eth), ConfigTask4(system), ConfigTask5(package)
            Model dependencies:
                ConfigTask2(service) from prev plan -> ConfigTask3(eth)
            QueryItem dependencies
            ms.items:
                ConfigTask3(eth) -> ConfigTask1(package)
            ms.system
                ConfigTask1(package) -> ConfigTask4(system)
            Call type + call id dependencies:
            (package, test6a)
                ConfigTask1(package) -> ConfigTask5(package)


        """
        ms = api.query('ms')[0]
        tasks = []
        pkg = ms.query('software-item')[0]
        #stor = ms.storage_profile
        if ms.is_initial():
            srv = ms.query('service-base')[0]
            cfg1 = ConfigTask(ms, pkg, "Plugin1 ConfigTask1",
                              "package", "test6")
            cfg1.requires.add(ms.system)
            tasks.append(cfg1)
            cfg2 = ConfigTask(ms, srv, "Plugin1 ConfigTask2",
                              "service", "test6")
            tasks.append(cfg2)
            cb1 = CallbackTask(pkg, "Plugin1 CallbackTask1", self._callback)
            cfg2.requires.add(cb1)
            tasks.append(cb1)
        elif pkg.is_applied():
            eth = ms.query('network-interface')[0]
            sys = ms.system
            cfg3 = ConfigTask(ms, eth, "Plugin1 ConfigTask3", "eth", "test6")
            cfg3.requires.add(ms.items)
            tasks.append(cfg3)
            cfg4 = ConfigTask(ms, sys, "Plugin1 ConfigTask4", "system", "test6")
            tasks.append(cfg4)
            cfg5 = ConfigTask(ms, pkg, "Plugin1 ConfigTask5",
                              "package", "test6a")
            tasks.append(cfg5)
            cb1 = CallbackTask(pkg, "Plugin1 CallbackTask1", self._callback)
            tasks.append(cb1)
        return tasks

    def _callback(self, *args):
        pass
