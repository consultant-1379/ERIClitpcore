from litp.core.plugin import Plugin
from litp.core.task import ConfigTask
from litp.core.task import CallbackTask


class Dummy200086Plugin(Plugin):

    def create_configuration(self, api):
        tasks = []
        for node in api.query("node"):
            for trigger_item in node.query("parent"):
                if trigger_item.is_initial():
                    tasks.append(
                        ConfigTask(node, trigger_item, "Install task", "foo",
                            "bar", ensure='present')
                    )
                elif trigger_item.is_for_removal():
                    # In this case, we create a deconfigure task that will
                    # transition the parent to Removed before the CleanupTasks
                    # for the collection and the child can run
                    if trigger_item.name == 'remove_parent':
                        tasks.append(
                            ConfigTask(node, trigger_item, "Removal task for parent item", "foo", "bar", ensure='absent')
                        )
                    elif trigger_item.name == 'remove_children':
                        for child_item in trigger_item.childs:
                            tasks.append(
                                ConfigTask(node, child_item, "Removal task for child item %s" % child_item.item_id, "foo", "bar", ensure='absent')
                            )
                    elif trigger_item.name == 'remove_collection':
                        tasks.append(
                            ConfigTask(node, trigger_item.childs, "Removal task for collection", "foo", "bar", ensure='absent')
                        )
        return tasks

    def create_lock_tasks(self, api, node):
        return (
            CallbackTask(node, "Lock CallbackTask", self._lock_callback),
            CallbackTask(node, "Unlock CallbackTask", self._unlock_callback),
        )

    def _lock_callback(self, api):
        pass

    def _unlock_callback(self, api):
        pass
