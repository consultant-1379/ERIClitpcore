from litp.core.plugin import Plugin
from litp.core.task import CallbackTask

class ParentChildInheritancePlugin(Plugin):
    """
    This plugin generates the ability to update a source property based on item name
    For example, if item name is 'prop1_new_repo' then the plugin will update the
    source item's property called 'myprop1' to the value 'new' when create_plan is invoked.

    mock-package item is used by plugin as a flag to control which source item is updated
    dummy-package item is used as Child item of Collection
    """

    def create_configuration(self, plugin_api_context):
        tasks = []

        for node in plugin_api_context.query("node"):
            for my_repo in node.query("myrepository"):
                tasks.append(CallbackTask(my_repo, "Dummy callback "
                    "task for {0}".format(my_repo.name), self._dummy_cb))
        return tasks

    def _dummy_cb(self, api):
        pass

    def update_model(self, plugin_api_context):
        for package in plugin_api_context.query("mock-package"):
            if package.get_vpath()=="/software/items/foo":
                if package.name in ("prop1_new_repo", "prop1_orig_repo", \
                    "updatable_new"):
                    update_src_flag = str(package.name)
                else:
                    update_src_flag = "anything"
        # Only update source (ref items don't return here)
        for my_repo in plugin_api_context.query("myrepository", name=update_src_flag, get_source=None):
            if my_repo.get_state() != "Initial":
                if my_repo.name == "prop1_new_repo":
                    my_repo.myprop1 = "new"
                elif my_repo.name == "prop1_orig_repo":
                    my_repo.myprop1 = "orig"

        for dummy_package in plugin_api_context.query("dummy-package", name=update_src_flag, get_source=None):
            if dummy_package.get_state() != "Initial":
                if dummy_package.name == "updatable_new":
                    dummy_package.updatable = "new"

