from litp.core.plugin import Plugin
from litp.core.execution_manager import ConfigTask


class Dummy11456Plugin(Plugin):

    def create_configuration(self, plugin_api_context):
        tasks = []
        nodes = plugin_api_context.query("node") + \
                plugin_api_context.query("ms")
        for node in nodes:
            for package in node.query("foo", is_initial=True):
                task = ConfigTask(node, package, "ConfigTask %s on %s" % (
                    package.name, node.hostname), "package",
                       package.name, **self._get_values(package))

                # Add item x to this tasks model_items (which will be removed)
                item_x = plugin_api_context.query_by_vpath("/software/items/x")

                if item_x:
                    task.model_items.add(item_x)
                tasks.append(task)
            for package in node.query("foo", is_updated=True):
                tasks.append(
                    ConfigTask(node, package, "Update", "package",
                               package.name,
                               **self._get_values(package))
                )
            for package in node.query("foo", is_for_removal=True):
                tasks.append(
                    ConfigTask(node, package, "deconfigure", "package",
                               package.name,
                               **self._get_removal_values(package))
                )
        return tasks

    def _get_values(self, item, applied=False):
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

    def _get_removal_values(self, item, applied=True):
        values = self._get_values(item, applied)
        values['ensure'] = "absent"
        return values
