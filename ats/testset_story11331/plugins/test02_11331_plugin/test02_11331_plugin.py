from litp.core.plugin import Plugin
from litp.core.task import ConfigTask
from litp.core.task import CallbackTask
import hashlib
from litp.core.litp_logging import LitpLogger
log = LitpLogger()


class Test11331Plugin(Plugin):
    """Dummy Yum Repo"""

    def __init__(self, *args, **kwargs):
        super(Test11331Plugin, self).__init__(*args, **kwargs)

    def create_configuration(self, api):
        tasks = []
        for node in api.query("node"):
            for yum_repo in node.query("yum-repository"):
                if yum_repo.get_state() in ("Initial", "Updated"):
                    tasks.append(
                        ConfigTask(node, yum_repo,
                            'ConfigTask for %s on node %s' \
                                % (yum_repo.name, node.hostname),
                            call_type="yumrepo",
                            call_id=yum_repo.properties.get('name'),
                            **yum_repo.properties
                        )
                    )
        return tasks

    def update_model(self, plugin_api_context):
        for sw in plugin_api_context.query("software"):
            for yum_repo in sw.query("yum-repository"):
                if yum_repo.name=="test_2a" and yum_repo.get_state() in ("Updated"):
                    yum_repo.clear_property('required_prop2')
                if yum_repo.name=="test_2b" and yum_repo.get_state() in ("Updated"):
                    yum_repo.clear_property('not_updatable_prop')
                if yum_repo.name=="test_2c":
                    yum_repo.clear_property('optional_prop')
                if yum_repo.name=="test_2d" and yum_repo.get_state() in ("Updated"):
                    yum_repo.clear_property('not_in_item_type_struture')
                if yum_repo.name=="test_2e" and yum_repo.get_state() in ("Updated"):
                    yum_repo.clear_property('not_a_property')
                if yum_repo.name=="test_2f":
                    yum_repo.clear_property('11331_prop')
                                         
        for node in plugin_api_context.query("node"):
             for yum_repo in node.query("yum-repository"):
                if yum_repo.name=="test_2a" and yum_repo.get_state() in ("Updated"):
                     yum_repo.clear_property('required_prop2')
                if yum_repo.name=="test_2b" and yum_repo.get_state() in ("Updated"):
                     yum_repo.clear_property('not_updatable_prop')
                if yum_repo.name=="test_2c":
                    yum_repo.clear_property('optional_prop')
                if yum_repo.name=="test_2d" and yum_repo.get_state() in ("Updated"):
                    yum_repo.clear_property('not_in_item_type_struture')
                if yum_repo.name=="test_2e" and yum_repo.get_state() in ("Updated"):
                    yum_repo.clear_property('not_a_property')
                if yum_repo.name=="test_2f":
                    yum_repo.clear_property('11331_prop')
