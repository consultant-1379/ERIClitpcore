from litp.core.plugin import Plugin
from litp.core.task import ConfigTask
from litp.core.task import CallbackTask
from litp.core.task import RemoteExecutionTask


class Dummy10168Plugin(Plugin):

    def __init__(self, *args, **kwargs):
        super(Dummy10168Plugin, self).__init__(*args, **kwargs)

    def create_configuration(self, api):
        tasks = []
        for clusteritem in api.query("cluster"):
            for node in clusteritem.nodes:
                if node.is_initial():
                    continue
                tasks.append(ConfigTask(node,node,"NodeItem_id=%s" % node.item_id, "foo", "bar"))
        return tasks

    def create_lock_tasks(self, api, node):
        ms = api.query("ms")[0]
        return (
            RemoteExecutionTask([node], ms, "Lock node %s" % node.vpath, "lock_unlock", "lock"),
            RemoteExecutionTask([node], ms, "Unlock node %s" % node.vpath, "lock_unlock", "unlock"),
            )
