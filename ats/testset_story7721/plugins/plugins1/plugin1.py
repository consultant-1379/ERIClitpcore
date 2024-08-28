from litp.core.plugin import Plugin
from litp.core.task import ConfigTask

from litp.core.litp_logging import LitpLogger
log = LitpLogger()


class Story7721Plugin(Plugin):
    def create_configuration(self, api):
        """Create configuration for Plan 1, Plan 2 of test_01 and removal plan
        of test_02"""
        ms = api.query('ms')[0]
        tasks = []
        eth = ms.query('network-interface')[0]
        if ms.is_initial():
            tasks.append(ConfigTask(ms, eth, "Plugin1 ConfigTask1",
                                    "eth", "test1", ensure='present'))
        elif eth.is_applied():
            # before it get's removed in test_02
            srv = ms.query('service-base')[0]
            tasks.append(ConfigTask(ms, srv, "Plugin1 ConfigTask2",
                                    "service", "test1"))
        return tasks
