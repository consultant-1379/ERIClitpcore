from litp.core.plugin import Plugin
from litp.core.task import ConfigTask
from litp.core.task import CallbackTask


class Dummy155243Plugin(Plugin):

    def create_configuration(self, api):
        tasks = []
        self.plugin = lambda: self
        cluster = api.query("cluster")[0]
        nodes = [node.hostname for node in cluster.nodes]

        # Create 2 tasks with their only difference being their dependencies
        for _ in xrange(2):
            task = CallbackTask(
                cluster,
                'Check VCS engine is running on cluster "{0}"'.format(
                    cluster.item_id),
                self.plugin().callback_method,
                callback_class='VcsCluster',
                callback_func="vcs_poll_callback",
                nodes=nodes)
            if tasks:
                task.requires.add(tasks[-1])
            tasks.append(task)

        return tasks

    def callback_method(self, api):
        pass
