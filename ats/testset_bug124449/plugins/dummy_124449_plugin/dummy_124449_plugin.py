from litp.core.plugin import Plugin
from litp.core.task import ConfigTask
from litp.core.task import CallbackTask


class Dummy124449Plugin(Plugin):

    def create_configuration(self, api):
        tasks = []
        ms_qi = api.query_by_vpath("/ms")
        for ms_service in ms_qi.query("vm-service"):
            # Removal case
            # This task is filtered out in the last plan as it is considered
            # identical to a "previously successful task"
            if ms_service.is_for_removal():
                tasks.append(
                    ConfigTask(
                        ms_qi,
                        ms_service,
                        "Deconfigure service Puppet resource",
                        "srv_image",
                        ms_service.item_id,
                        ensure="absent"
                    )
                )
                # Cause node-bound tasks to fail
                for node in api.query("node"):
                    tasks.append(CallbackTask(node, "Deconfigure cb task",
                        self._fail_callback))
            elif ms_service.is_initial():
                tasks.append(
                    ConfigTask(
                        ms_qi,
                        ms_service,
                        "Service Puppet resource",
                        "srv_image",
                        ms_service.item_id
                    )
                )
        return tasks

    def create_lock_tasks(self, api, node):
        ms = api.query("ms")[0]
        return (
            ConfigTask(ms, node, "lock ConfigTask", "node_lock", "blah1"),
            ConfigTask(ms, node, "unlock ConfigTask", "node_unlock", "blah2"),
        )

    def _fail_callback(self, api):
        raise Exception
