from litp.core.plugin import Plugin
from litp.core.task import ConfigTask
from litp.core.task import CallbackTask

from litp.core.litp_logging import LitpLogger
log = LitpLogger()


class Story7721Plugin(Plugin):
    def create_configuration(self, api):
        """
        Plan1:
            Create ConfigTask1(eth)
        Plan2: /
            Create ConfigTask1(eth) - wil get filtered
        Plan3
            Create ConfigTask1(eth) deconfigure task
        """

        ms = api.query('ms')[0]
        tasks = []
        eth = ms.query('network-interface')[0]
        cfg1 = ConfigTask(ms, eth, "Plugin1 ConfigTask1",
                          "eth", "test8")
        cfg2 = ConfigTask(ms, eth, "Plugin1 ConfigTask2", "eth_dependent",
                          "test8")
        cfg2.requires.add(cfg1)
        tasks.append(cfg1)
        tasks.append(cfg2)
        return tasks

    def _callback(self, *args):
        pass
