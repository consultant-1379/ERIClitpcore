from litp.core.plugin import Plugin
from litp.core.task import ConfigTask
from litp.core.task import CallbackTask
import hashlib


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
        for node in plugin_api_context.query("node"):
            for yum_repo in node.query("yum-repository"):
                if yum_repo.name=="test03":
                    if not yum_repo.checksum:
                        # Set the checksum property
                        md5sum = hashlib.md5('dummy_value').hexdigest()
                        yum_repo.checksum = md5sum
                    else:
                        # Try to unset the checksum
                        yum_repo.clear_property('checksum')
                        yum_repo.clear_property('required_prop1')
                        yum_repo.clear_property('optional_prop1')
                elif yum_repo.name=="test01" and yum_repo.get_state() in ("Updated"):
                    yum_repo.clear_property('optional_prop1')
                elif yum_repo.name=="test01a" and yum_repo.get_state() in ("Updated"):
                        yum_repo.clear_property('ac1_prop')
                elif yum_repo.name=="test01c" and yum_repo.get_state() in ("Updated"):
                        yum_repo.clear_property('ac6_prop')
                        yum_repo.clear_property('ac7_prop')
                        yum_repo.clear_property('ac9_prop')
                elif yum_repo.name=="t3_a":
                        yum_repo.clear_property('ac3_prop')
                elif yum_repo.name=="t4_c":
                        yum_repo.clear_property('ac3_prop')

        for sw in plugin_api_context.query("software"):
            for yum_repo in sw.query("yum-repository"):
                if yum_repo.name=="test01" and yum_repo.get_state() in ("Updated"):
                    yum_repo.clear_property('required_prop1')
                    yum_repo.clear_property('optional_prop1')
                if yum_repo.name=="test01a" and yum_repo.get_state() in ("Updated"):
                    yum_repo.clear_property('ac1_prop')
                if yum_repo.name=="test01b" and yum_repo.get_state() in ("Updated"):
                    yum_repo.clear_property('ac2_prop')
