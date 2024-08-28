from litp.core.plugin import Plugin
from litp.core.task import ConfigTask

from litp.core.litp_logging import LitpLogger
log = LitpLogger()


class Story7721Plugin(Plugin):
    def create_configuration(self, api):
        """
        Plan1:
            Create ConfigTask1(package), ConfigTask2(service)
            Model dependencies:
                none
        Plan2
            Create ConfigTask3(eth)
            Model dependencies:
                ConfigTask2(service) from prev plan -> ConfigTask3(eth)
            QueryItem dependencies (ms.items):
                ConfigTask3(eth) -> ConfigTask1(package)
        """
        ms = api.query('ms')[0]
        tasks = []
        if ms.is_initial():
            srv = ms.query('service-base')[0]
            pkg = ms.query('software-item')[0]
            tasks.append(ConfigTask(ms, srv, "Plugin1 ConfigTask2",
                                    "service", "test4"))
            tasks.append(ConfigTask(ms, pkg, "Plugin1 ConfigTask1",
                                    "package", "test4"))
        else:
            eth = ms.query('network-interface')[0]
            cfg = ConfigTask(ms, eth, "Plugin1 ConfigTask3",
                             "eth", "test4", ensure='present')
            cfg.requires.add(ms.items)
            tasks.append(cfg)
        return tasks
