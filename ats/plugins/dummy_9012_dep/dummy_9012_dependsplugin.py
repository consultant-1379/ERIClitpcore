from litp.core.plugin import Plugin
from litp.core.task import ConfigTask

from litp.core.litp_logging import LitpLogger
log = LitpLogger()


class Story7721DependsPlugin(Plugin):

    @staticmethod
    def _config_task(node_item, model_item, kwargs):
        description = "ConfigTask {0} on node {1}".format(
            model_item.name, node_item.hostname
        )
        return ConfigTask(
            node_item, model_item, description, "notify",
            "call_id_{0}".format(model_item.name), **kwargs
        )

    def _test_01_02_03_04_05(self, node_item, model_item, depends_query):
        tasks = list()
        task = None
        # test_01/test_02/test_03/test_04: dependency story-7721a query item
        # test_05: dependency story-7721b query item
        if model_item.is_initial() or model_item.is_updated() or \
                model_item.is_applied():
            kwargs = {"message": model_item.name}
            task = self._config_task(node_item, model_item, kwargs)
        if task:
            config_items = node_item.query(depends_query)
            if config_items:
                for config_item in config_items:
                    task.requires.add(config_item)
            tasks.append(task)
        return tasks

    def create_configuration(self, api):
        tasks = list()
        ms_ = api.query("ms")[0]
        software_items = ms_.query("depend-story-7721")
        for sw_ in software_items:
            if 'test_01' in sw_.name or 'test_04' in sw_.name:
                depends_query = "story-7721a"
            elif 'test_05' in sw_.name:
                depends_query = "story-7721b"
            tasks.extend(self._test_01_02_03_04_05(ms_, sw_, depends_query))
        return tasks
