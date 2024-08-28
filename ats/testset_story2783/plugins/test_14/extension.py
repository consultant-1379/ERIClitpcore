from litp.core.model_type import ItemType, Property, View
from litp.core.extension import ModelExtension

from litp.core.litp_logging import LitpLogger
log = LitpLogger()


class Story2783Extension(ModelExtension):
    """
    Story2783 Model Extension
    """

    def define_item_types(self):
        return [
            ItemType(
                'story2783',
                extend_item='software-item',
                name=Property('any_string'),
                rest_only=Property('any_string', updatable_plugin=False),
                plugin_only=Property('any_string', updatable_plugin=True,
                                     updatable_rest=False),
                both=Property('any_string', updatable_plugin=True),
                none=Property('any_string', updatable_plugin=False,
                              updatable_rest=False),
                view=View('any_string', Story2783Extension.fubar)
            )
        ]

    @staticmethod
    def fubar(api, query_item):
        log.trace.debug(api)
        log.trace.debug(query_item)
        return 'FUBAR'
