from litp.core.plugin import Plugin
from litp.core.task import CallbackTask, ConfigTask


class DummyPlugin(Plugin):

    def create_configuration(self, api):
        node = api.query_by_vpath("/deployments/local/clusters/cluster1/nodes/node1")

        container = api.query_by_vpath("/software/profiles/container")
        container_task = ConfigTask(node, container, "Container ConfigTask", "container_call", "id3")

        cb = CallbackTask(node, "Container CallbackTask", self._cb)
        cb.requires.add(container_task)

        child = api.query_by_vpath("/software/profiles/container/child")
        child_task = ConfigTask(node, child, "Child ConfigTask", "child_call", "id1")

        child_task.requires.add(cb)

        cb_2 = CallbackTask(node, "Child CallbackTask", self._cb2)
        cb_2.requires.add(child_task)

        ref = api.query_by_vpath("/software/profiles/container/ref")
        ref_task = ConfigTask(node, ref, "Reference ConfigTask", "ref_call", "id2")
        ref_task.requires.add(cb_2)

        return [container_task, cb_2, cb, child_task, ref_task]

    def _cb(self, api):
        pass

    def _cb2(self, api):
        pass
