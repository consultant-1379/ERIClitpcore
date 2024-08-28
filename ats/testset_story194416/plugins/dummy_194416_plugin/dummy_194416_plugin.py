from litp.core.plugin import Plugin
from litp.core.task import ConfigTask
from litp.core.task import CallbackTask


class Dummy194416Plugin(Plugin):

    def create_configuration(self, api):
        tasks = []
        for node in api.query("node"):
            for trigger_item in node.query("trigger-194416"):
                if trigger_item.behaviour.endswith('configtask'):
                    if trigger_item.is_initial():
                        configure_task = ConfigTask(
                            node,
                            trigger_item,
                            "Persistent ConfigTask for node-bound item",
                            'resource_194416',
                            'configure_%s' % trigger_item.item_id,
                            ensure='present'
                        )
                        tasks.append(configure_task)
                    if trigger_item.behaviour.startswith('config-and-deconfig'):
                        if trigger_item.is_for_removal():
                            configure_task = ConfigTask(
                                node,
                                trigger_item,
                                "Removal ConfigTask for node-bound item",
                                'resource_194416',
                                'configure_%s' % trigger_item.item_id,
                                ensure='absent'
                            )
                            tasks.append(configure_task)

                elif trigger_item.behaviour.endswith('callbacktask'):
                    if trigger_item.is_initial():
                        cb_task = CallbackTask(
                            trigger_item,
                            "CallbackTask for node-bound item",
                            self._noop_callback
                        )
                        tasks.append(cb_task)
                    if trigger_item.behaviour.startswith('config-and-deconfig'):
                        if trigger_item.is_for_removal():
                            cb_task = CallbackTask(
                                trigger_item,
                                "Removal CallbackTask for node-bound item",
                                self._noop_callback
                            )
                            tasks.append(cb_task)
        return tasks

    def create_lock_tasks(self, api, node):
        ms = api.query("ms")[0]
        return (
            ConfigTask(ms, node, "lock ConfigTask", "node_lock", "blah1"),
            ConfigTask(ms, node, "unlock ConfigTask", "node_unlock", "blah2"),
        )

    def _fail_callback(self, api):
        raise Exception

    def _noop_callback(self, api):
        pass
