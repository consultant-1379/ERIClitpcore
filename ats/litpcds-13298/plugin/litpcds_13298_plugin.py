from litp.core.plugin import Plugin
from litp.core.task import ConfigTask


class Plugin_13298(Plugin):

    def create_configuration(self, api):
        tasks = []

        # Generate a persistent ConfigTask with a dependency against a
        # non-persistent ConfigTask when the flag item does not exist
        if not api.query_by_vpath('/software/items/flag'):
            for node in sorted(api.query("node") + api.query("ms")):
                p_task = ConfigTask(node, node, "Persistent ConfigTask", "p_task", "t1")
                np_task = ConfigTask(node, node, "Non-persistent ConfigTask", "np_task", "t1")
                np_task.persist = False
                p_task.requires.add(np_task)

                tasks.extend([p_task, np_task])
        else:
            ms = api.query_by_vpath('/ms')
            other_task = ConfigTask(ms, ms, "Unrelated task", "something", "other")
            tasks.append(other_task)
        return tasks
