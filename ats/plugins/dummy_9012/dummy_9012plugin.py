import time
from litp.core.plugin import Plugin
from litp.core.task import ConfigTask
from litp.core.task import CallbackTask

from litp.core.litp_logging import LitpLogger
log = LitpLogger()


class Story7721Plugin(Plugin):

    @staticmethod
    def _config_task_description(node_item, model_item, deconfigure=False):
        if deconfigure:
            description = "ConfigTask deconfigure {0} on node {1}"
        else:
            description = "ConfigTask {0} on node {1}"
        return description.format(model_item.name, node_item.hostname)

    @staticmethod
    def _config_task(node_item, model_item, description, kwargs):
        return ConfigTask(
            node_item, model_item, description, "notify",
            "call_id_{0}".format(model_item.name), **kwargs
        )

    def cb_simple_callback(self, api):
        time.sleep(60)
        log.trace.debug(api)

    def _callback_task(self, model_item):
        description = "standalone CallbackTask {0}".format(model_item.name)
        return CallbackTask(model_item, description, self.cb_simple_callback)

    @staticmethod
    def _config_items(node_item, item_type):
        return node_item.query(item_type)

    def _test_01_02_03(self, node_item, model_item):
        tasks = list()
        task = None
        task_ = None
        # test_01/test_02: remove no deconfigure task
        if model_item.is_initial() or model_item.is_updated():
            description = self._config_task_description(node_item, model_item)
            kwargs = {"message": model_item.name}
            task = self._config_task(
                node_item, model_item, description, kwargs
            )
        # test_01/test_03: remove with deconfigure task
        if model_item.is_for_removal() and model_item.deconfigure == 'true':
            description = self._config_task_description(
                node_item, model_item, deconfigure=True
            )
            kwargs = {"message": "{0}_deconfigure".format(model_item.name)}
            task = self._config_task(
                node_item, model_item, description, kwargs
            )
            task_ = self._callback_task(model_item)
        if task:
            if task_:
                task_.requires.add(task)
                tasks.append(task_)
            tasks.append(task)
        return tasks

    def _test_04(self, node_item, model_item):
        tasks = list()
        task = None
        # test_04: task requires query item second plugin depend-story-7721
        if model_item.is_initial() or model_item.is_updated() or \
                model_item.is_applied():
            description = self._config_task_description(node_item, model_item)
            kwargs = {"message": model_item.name}
            task = self._config_task(
                node_item, model_item, description, kwargs
            )
        if task:
            #if model_item._item_type == "story-7721b":
            software_items = node_item.query("depend-story-7721")
            if software_items:
                for sw_ in software_items:
                    task.requires.add(sw_)
            tasks.append(task)
        return tasks

    def _test_05(self, node_item, model_item, tasks=None):
        # if tasks=None, create new tasks list
        if not tasks:
            tasks = list()
        task1 = None
        task2 = None
        # test_05: config task story-7721a requires callback task which
        if model_item.is_initial() or model_item.is_updated():
            description = self._config_task_description(node_item, model_item)
            kwargs = {"message": model_item.name}
            task1 = self._config_task(
                node_item, model_item, description, kwargs
            )
            # if the tasks list is empty
            if task1 and not tasks:
                tasks.append(task1)
                task2 = self._callback_task(model_item)
                if task2:
                    task2.requires.add(task1)
                    tasks.append(task2)
            # if the task list is not empty, task requires last task in list
            else:
                task1.requires.add(tasks[-1])
                tasks.append(task1)
        return tasks

    def create_configuration(self, api):
        tasks = list()
        ms_ = api.query("ms")[0]
        configs_7721a = self._config_items(ms_, "story-7721a")
        configs_7721b = self._config_items(ms_, "story-7721b")
        for config_item in configs_7721a:
            if 'test_01' in config_item.name:
                tasks.extend(self._test_01_02_03(ms_, config_item))
            elif 'test_04' in config_item.name:
                tasks.extend(self._test_04(ms_, config_item))
                if configs_7721b:
                    for config_item_ in configs_7721b:
                        tasks.extend(self._test_04(ms_, config_item_))
            elif 'test_05' in config_item.name and configs_7721b:
                tasks.extend(self._test_05(ms_, config_item))
                if tasks:
                    for config_item_ in configs_7721b:
                        tasks.extend(self._test_05(ms_, config_item_, tasks))
        return tasks
