from litp.core.plugin import Plugin
from litp.core.task import ConfigTask
from litp.core.task import CallbackTask


class Dummy11331Plugin(Plugin):
    """Dummy Yum Repo"""

    def __init__(self, *args, **kwargs):
        super(Dummy11331Plugin, self).__init__(*args, **kwargs)

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
                if (yum_repo.get_state() == 'Updated' and
                        not yum_repo.applied_properties_determinable):
                    yum_repo.clear_property('optional_prop')
