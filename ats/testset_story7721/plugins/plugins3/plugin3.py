from litp.core.plugin import Plugin
from litp.core.task import ConfigTask
from litp.core.task import CallbackTask

from litp.core.litp_logging import LitpLogger
log = LitpLogger()


class Story7721Plugin(Plugin):
    def create_configuration(self, api):
        """
        Plan1:
            Create ConfigTask1(eth), ConfigTask2(service)
            Model dependencies:
                ConfigTask2(service) -> ConfigTask1(eth)
        Plan2
            Create ConfigTask1(eth) deconfigure task
            Create helper CallbackTask to force creation of 2nd phase
            Model dependencies:
                ConfigTask2(service) from prev plan -> ConfigTask1(eth)
        """

        ms = api.query('ms')[0]
        tasks = []
        eth = ms.query('network-interface')[0]
        srv = ms.query('service-base')[0]
        if ms.is_initial():
            tasks.append(ConfigTask(ms, eth, "Plugin1 ConfigTask1",
                                    "eth", "test3", ensure='present'))
            tasks.append(ConfigTask(ms, srv, "Plugin1 ConfigTask2",
                                    "service", "test3"))
        else:
            cfg = ConfigTask(ms, eth, "Plugin1 ConfigTask1 deconfigure",
                             "eth", "test3", ensure='absent')
            tasks.append(cfg)
            cb = CallbackTask(eth, "enforce 2nd phase", self._callback)
            cb.requires.add(cfg)
            tasks.append(cb)
        return tasks

    def _callback(self, *args):
        pass
