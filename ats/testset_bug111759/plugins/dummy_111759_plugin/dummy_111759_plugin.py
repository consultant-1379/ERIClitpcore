from litp.core.plugin import Plugin
from litp.core.task import CallbackTask


class Dummy111759Plugin(Plugin):

    def create_configuration(self, api):
        tasks = []
        ms_qi = api.query("ms")[0]
        for threefold_qi in ms_qi.query("three_children"):
            left_child_task = CallbackTask(
                threefold_qi.left,
                "Left child task",
                self._pass_callback
            )
            right_child_task = CallbackTask(
                threefold_qi.right,
                "Right child task",
                self._pass_callback
            )

            tasks.extend([left_child_task, right_child_task])

        return tasks

    def _pass_callback(self, api):
        pass
