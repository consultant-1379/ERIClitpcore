from litp.core.plugin import Plugin
from litp.core.task import ConfigTask
from litp.core.task import CallbackTask
from litp.core.task import RemoteExecutionTask


class Dummy13721Plugin(Plugin):

    def create_configuration(self, api):
        tasks = []

        node_qi = api.query("node", hostname="node1")[0]
        node_task = ConfigTask(node_qi, node_qi, "Passing task on node1",
            "foo", "bar")
        tasks.append(node_task)

        for system_qi in node_qi.query("system"):
            system_task = CallbackTask(system_qi,
                "Failing CallbackTask on node system",
                self._fail_callback
            )
            system_task.model_items.add(node_qi)
            tasks.append(system_task)

        node_qi = api.query("node", hostname="node2")[0]
        node_task = ConfigTask(node_qi, node_qi, "Passing task on node2",
            "foo", "bar")
        tasks.append(node_task)


        for system_qi in node_qi.query("system"):
            system_task = RemoteExecutionTask(
                [node_qi], system_qi,
                "Failing RemoteExecutionTask on node system",
                "secret_agent_man",
                "they_gave_you_a_number_and_took_away_your_name",
            )
            system_task.model_items.add(node_qi)
            tasks.append(system_task)
        return tasks

    def create_lock_tasks(self, api, node):
        ms = api.query("ms")[0]
        return (
            ConfigTask(ms, node, "lock ConfigTask", "node_lock", "blah1"),
            ConfigTask(ms, node, "unlock ConfigTask", "node_unlock", "blah2"),
        )

    def _fail_callback(self, api):
        raise Exception
