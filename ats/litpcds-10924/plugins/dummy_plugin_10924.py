from litp.core.plugin import Plugin
from litp.core.execution_manager import ConfigTask, CallbackTask
from litp.core.litp_logging import LitpLogger
from litp.core.validators import ValidationError


_LOG = LitpLogger()


class DummyPlugin10924(Plugin):

    def create_configuration(self, plugin_api_context):
        tasks = []
        ms_qi = plugin_api_context.query("ms")[0]

        for service_qi in ms_qi.query('distro-service'):
            if service_qi.is_initial() or service_qi.is_applied():
                tasks.append(
                    ConfigTask(
                        ms_qi,
                        service_qi,
                        "Distro task",
                        "cobblerdata::import_distro",
                        service_qi.name
                    )
                )
                tasks.append(
                    CallbackTask(
                        ms_qi,
                        "Unrelated task",
                        DummyPlugin10924._dummy_callback,
                    )
                )
                tasks[1].requires.add(tasks[0])
        return tasks

    def _dummy_callback(self, callback_api):
        pass
