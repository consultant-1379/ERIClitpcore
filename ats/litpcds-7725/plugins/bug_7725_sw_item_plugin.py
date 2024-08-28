from litp.core.plugin import Plugin
from litp.core.task import CallbackTask

from litp.core.litp_logging import LitpLogger
log = LitpLogger()


class Bug7725Plugin(Plugin):

    def callbacktask_handler(self, callback_api):
        pass

    def create_configuration(self, api):
        nodes = api.query('ms')
        nodes.extend(api.query('node'))
        for node in nodes:
            sw_items = node.query('bug7725-sw-item')
            if sw_items:
                for sw_item in sw_items:
                    if sw_item.is_initial() or sw_item.is_updated():
                        return [
                            CallbackTask(
                                sw_item,
                                "Dummy task (single), source {0}".format(
                                    sw_item.get_source().get_vpath()
                                ),
                                self.callbacktask_handler
                            )
                        ]
        # remove nonexistent
        return []
