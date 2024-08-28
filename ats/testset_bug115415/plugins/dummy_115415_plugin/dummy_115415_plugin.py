from litp.core.plugin import Plugin
from litp.core.task import ConfigTask
from litp.core.task import CallbackTask


class Dummy115415Plugin(Plugin):

    def create_configuration(self, api):
        tasks = []
        ms_qi = api.query_by_vpath('/ms')
        for item in ms_qi.query("trigger"):
            cfgA = ConfigTask(
                ms_qi,
                item,
                "Task A: %s" % item.name,
                "foo",
                item.item_id,
                param=item.name
            )
            cfgA.model_items.add(ms_qi)
            tasks.append(cfgA)

            if item.is_initial():
                cfgB = ConfigTask(
                    ms_qi,
                    item,
                    "Task B: %s" % item.name,
                    "bar",
                    item.item_id
                )
                cfgB.model_items.add(ms_qi)
                cfgB.requires.add(cfgA)
                tasks.append(cfgB)

        return tasks

    def create_lock_tasks(self, api, node):
        ms = api.query("ms")[0]
        return (
            ConfigTask(ms, node, "lock ConfigTask", "node_lock", "blah1"),
            ConfigTask(ms, node, "unlock ConfigTask", "node_unlock", "blah2"),
        )

    def _fail_callback(self, api):
        raise Exception
