from litp.core.plugin import Plugin
from litp.core.task import CallbackTask

from litp.core.litp_logging import LitpLogger
log = LitpLogger()


class Story6861Plugin(Plugin):

    def cb_fail_regex_validation(self, api):
        modelitems = api.query('story6861', is_initial=True)
        modelitem = modelitems[0]
        modelitem.fail = 'not_a_path_property'

    def cb_fail_prop_validation(self, api):
        modelitems = api.query('story6861', is_initial=True)
        modelitem = modelitems[0]
        modelitem.description = ''

    def cb_fail_model_item_validation(self, api):
        modelitems = api.query('story6861', is_initial=True)
        modelitem = modelitems[0]
        modelitem.fail = '/fail/path/property'

    def create_configuration(self, plugin_api_context):

        tasks = list()
        modelitems = plugin_api_context.query('story6861', is_initial=True)
        modelitem = modelitems[0]
        if modelitem.name == 'test_01':
            tasks.append(
                CallbackTask(
                    modelitem,
                    'fail regex validation',
                    self.cb_fail_regex_validation
                )
            )
        elif modelitem.name == 'test_02':
            tasks.append(
                CallbackTask(
                    modelitem,
                    'fail property validation',
                    self.cb_fail_prop_validation
                )
            )
        elif modelitem.name == 'test_03':
            tasks.append(
                CallbackTask(
                    modelitem,
                    'fail model item validation',
                    self.cb_fail_model_item_validation
                )
            )

        return tasks
