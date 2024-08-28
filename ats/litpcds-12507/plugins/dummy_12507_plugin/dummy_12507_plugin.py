from litp.core.plugin import Plugin
from litp.core.execution_manager import ConfigTask


class Dummy12507Plugin(Plugin):

    def create_configuration(self, plugin_api_context):
        """
        Don't return a removal task for ForRemoval item. But return task on
        the same node hanging off a different item, with same call_type and
        call_id.
        """

        tasks = []
        nodes = plugin_api_context.query("node") + \
                plugin_api_context.query("ms")
        node1 = plugin_api_context.query_by_vpath("/deployments/local/clusters/cluster1/nodes/node1")
        for node in nodes:
            for package in node.query("dummy-12507-package", is_initial=True):
                tasks.append(
                    ConfigTask(node, package, "Description", "package",
                               package.name,
                               **self._get_values(package))
                )
            for package in node.query("mock-package", is_updated=True):
                tasks.append(
                    ConfigTask(node, package, "Update", "package",
                               package.name,
                               **self._get_values(package))
                )
            # Instead of returning removal tasks, return a ConfigTask with same
            # call_type call_id as persisted ConfigTask with ForRemoval item.
            # Using the same node (ms) hanging off a different model item.
            for package in node.query("dummy-12507-package", is_for_removal=True):
                tasks.append(
                        ConfigTask(node, node1, "Same call_type and call_id, differnt item",
                        "package", "foo")
                )
        return tasks

    def _get_values(self, item, applied=False):
        # get configuration values from items properties for a task
        values = {}
        ensure = item.ensure
        if ensure:
            values['ensure'] = ensure
        if item.version:
            if item.release:
                if applied:
                    values['ensure'] = '-'.join([item.version,
                                             item.release])
                else:
                    values['ensure'] = '-'.join([
                        item.applied_properties.get("version", None),
                        item.applied_properties.get("release", None)])
            else:
                if applied:
                    values['ensure'] = item.version
                else:
                    values['ensure'] = item.applied_properties.get(
                                                            "version", None)
        repo = item.repository

        permanent_repos = ['OS', 'CUSTOM', 'UPDATES', 'LITP']
        if repo and repo not in permanent_repos:
            values['require'].extend([{'type':
                                    'Yum::Repo', 'value': repo}])
        config = item.config
        if config:
            values['configfiles'] = config
        return values
