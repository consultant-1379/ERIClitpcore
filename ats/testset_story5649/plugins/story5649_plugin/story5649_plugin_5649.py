from litp.core.plugin import Plugin
from litp.core.task import CallbackTask


class Story5649Plugin(Plugin):
    """test plugin for LITPCDS-5649"""

    def create_configuration(self, api):
        tasks = []

        items = api.query('story5649', is_initial=True)
        for item in sorted(items, key=lambda qitem: qitem.name):
            extra_items = set()
            if item.extra_items is not None:
                for extra_item_name in item.extra_items.split(','):
                    extra_item = api.query_by_vpath('/ms/items/' +
                            extra_item_name)
                    if extra_item:
                        extra_items.add(extra_item)

            task1 = CallbackTask(item, 'cb_success_1 {0}'.format(item.name),
                    self.cb_success_1)
            task1.model_items.update(extra_items)
            tasks.append(task1)

            if item.number_of_tasks == 'many':
                task2 = CallbackTask(item, 'cb_success_2 {0}'.format(item.name),
                        self.cb_success_2)
                task2.model_items.update(extra_items)
                tasks.append(task2)

                task3 = CallbackTask(item, 'cb_success_3 {0}'.format(item.name),
                        self.cb_success_3)
                task3.model_items.update(extra_items)
                tasks.append(task3)
        return tasks

    def cb_success_1(self):
        pass

    def cb_success_2(self):
        pass

    def cb_success_3(self):
        pass
