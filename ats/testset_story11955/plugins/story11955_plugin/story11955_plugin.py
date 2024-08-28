from litp.core.plugin import Plugin
from litp.core.task import ConfigTask
from litp.core.task import CallbackTask
from litp.core.task import RemoteExecutionTask
from litp.core.task import OrderedTaskList


class Story11955Plugin(Plugin):
    """Test plugin for LITPCDS-11955"""

    def create_configuration(self, api):
        tasks = []
        node = api.query('node')[0]
        for item in sorted(node.query('story11955', is_initial=True)):
            # Test case 01
            if item.testcase == 'tc1':
                if item.item_id == 'item1b':
                    tasks.append(ConfigTask(node, item,
                            'tc1 Config task for item 1b',
                            'tc1_res_1b', 'tc1_title_1b'))
                    tasks.append(CallbackTask(item, 'tc1 callback task for item 1b',
                        Story11955Plugin._cb))

                elif item.item_id == 'item2b':
                    tasks.append(ConfigTask(node, item,
                            'tc1 Config task for item 2b',
                            'tc1_res_2b', 'tc1_title_2b'))
                    tasks.append(CallbackTask(item, 'tc1 callback task for item 2b',
                        Story11955Plugin._cb))

            # Test case 02
            elif item.testcase == 'tc2':
                if item.item_id == 'item1b':
                    tasks.append(ConfigTask(node, item,
                            'tc2 Config task for item 1b',
                            'tc2_res_1b', 'tc2_title_1b'))
                    tasks.append(RemoteExecutionTask([node], item,
                        "RemoteExecution task 1b", "lock_unlock",
                        "lock_a"))

                elif item.item_id == 'item2b':
                    tasks.append(ConfigTask(node, item,
                            'tc2 Config task for item 2b',
                            'tc2_res_2b', 'tc2_title_2b'))
                    tasks.append(RemoteExecutionTask([node], item,
                        "RemoteExecution task 2b", "lock_unlock",
                        "lock_b"))

            # Test case 03
            elif item.testcase == 'tc3':
                if item.item_id == 'item1b':
                    tasks.append(ConfigTask(node, item,
                            'tc3 Config task for item 1b',
                            'tc3_res_1b', 'tc3_title_1b'))
                    tasks.append(CallbackTask(item, 'tc3 callback task for item 1b',
                        Story11955Plugin._cb))
                    tasks.append(RemoteExecutionTask([node], item,
                        "tc3 RemoteExecution task 1b", "lock_unlock_a",
                        "lock_a"))

                elif item.item_id == 'item2b':
                    tasks.append(ConfigTask(node, item,
                            'tc3 first Config task for item 2b',
                            'tc3_res_2b_first', 'tc3_title_2b_first'))
                    tasks.append(ConfigTask(node, item,
                            'tc3 second Config task for item 2b',
                            'tc3_res_2b_second', 'tc3_title_2b_second'))
                    tasks.append(CallbackTask(item, 'tc3 first callback task for item 2b',
                        Story11955Plugin._cb1))
                    tasks.append(CallbackTask(item, 'tc3 second callback task for item 2b',
                        Story11955Plugin._cb2))
                    task_remote_2b = RemoteExecutionTask([node], item,
                        "tc3 first RemoteExecution task 2b", "lock_unlock_b",
                        "lock_b")
                    tasks.append(task_remote_2b)
                    tasks.append(RemoteExecutionTask([node], item,
                        "tc3 second RemoteExecution task 2b", "lock_unlock_c",
                        "lock_c"))

                elif item.item_id == 'item3b':
                    task_callback_3b = CallbackTask(item, 'tc3 callback task for item 3b',
                        Story11955Plugin._cb)
                    # Dependency: callback task associated with model item 3b
                    # requires remote execution task associated with model item 2b
                    task_callback_3b.requires.add(task_remote_2b)
                    tasks.append(task_callback_3b)

                elif item.item_id == 'item4b':
                    task_remote_4b = (RemoteExecutionTask([node], item,
                        "tc3 RemoteExecution task 4b", "lock_unlock_d",
                        "lock_d"))
                    # Dependency: remote execution task associated with model item 4b
                    # requires callback task associated with model item 3b
                    task_remote_4b.requires.add(task_callback_3b)
                    tasks.append(task_remote_4b)

                elif item.item_id == 'item5b':
                    tasks.append(ConfigTask(node, item,
                            'tc3 Config task for item 5b',
                            'tc3_res_5b', 'tc3_title_5b'))

            # Test case 04
            elif item.testcase == 'tc4':
                if item.item_id == 'item1b':
                    ordered_tasks = []
                    tasks.append(ConfigTask(node, item,
                            'tc4 first Config task for item 1b',
                            'tc4_res_1b', 'tc4_title_1b'))
                    ordered_tasks.append(CallbackTask(item, 'tc4 ordered callback task for item 1b',
                        Story11955Plugin._cb))
                    ordered_tasks.append(ConfigTask(node, item,
                            'tc4 ordered Config task for item 1b',
                            'tc4_res_1b_ordered', 'tc4_title_1b_ordered'))
                    tasks.append(OrderedTaskList(item, ordered_tasks))

                elif item.item_id == 'item2b':
                    ordered_tasks = []
                    tasks.append(ConfigTask(node, item,
                            'tc4 first Config task for item 2b',
                            'tc4_res_2b', 'tc4_title_2b'))
                    ordered_tasks.append(CallbackTask(item, 'tc4 ordered callback task for item 2b',
                        Story11955Plugin._cb))
                    ordered_tasks.append(ConfigTask(node, item,
                            'tc4 ordered Config task for item 2b',
                            'tc4_res_2b_ordered', 'tc4_title_2b_ordered'))
                    tasks.append(OrderedTaskList(item, ordered_tasks))

            # Test case 05
            elif item.testcase == 'tc5':
                if item.item_id == 'item1b':
                    task_callback_1 = CallbackTask(item, 'tc5 first callback task for item 1b',
                        Story11955Plugin._cb1)
                    task_callback_2 = CallbackTask(item, 'tc5 second callback task for item 1b',
                        Story11955Plugin._cb2)
                    task_callback_2.requires.add(task_callback_1)
                    tasks.extend([task_callback_1, task_callback_2])

                elif item.item_id == 'item2b':
                    tasks.append(ConfigTask(node, item,
                            'tc5 first Config task for item 2b',
                            'tc5_res_2b_first', 'tc5_title_2b_first'))
                    tasks.append(ConfigTask(node, item,
                            'tc5 second Config task for item 2b',
                            'tc5_res_2b_second', 'tc5_title_2b_second'))

            # Test case 06
            elif item.testcase == 'tc6':
                if item.item_id == 'item1b':
                    task_callback_1 = CallbackTask(item, 'tc6 first callback task for item 1b',
                        Story11955Plugin._cb1)
                    task_callback_2 = CallbackTask(item, 'tc6 second callback task for item 1b',
                        Story11955Plugin._cb2)
                    tasks.extend([task_callback_1, task_callback_2])

                elif item.item_id == 'item2b':
                    task_config_1 = ConfigTask(node, item,
                            'tc6 first Config task for item 2b',
                            'tc6_res_2b_first', 'tc6_title_2b_first')
                    task_config_2 = ConfigTask(node, item,
                            'tc6 second Config task for item 2b',
                            'tc6_res_2b_second', 'tc6_title_2b_second')
                    task_config_1.requires.add(task_callback_1)
                    task_config_2.requires.add(task_callback_2)
                    task_callback_2.requires.add(task_config_1)
                    tasks.extend([task_config_1, task_config_2])

            # Test case 07
            elif item.testcase == 'tc7':
                if item.item_id == 'item1b':
                    task_remote_1 = RemoteExecutionTask([node], item,
                        "tc7 first RemoteExecution task 1b", "lock_unlock_a",
                        "lock_a")
                    task_remote_2 = RemoteExecutionTask([node], item,
                        "tc7 second RemoteExecution task 1b", "lock_unlock_b",
                        "lock_b")
                    task_remote_2.requires.add(task_remote_1)
                    tasks.extend([task_remote_1, task_remote_2])

                elif item.item_id == 'item2b':
                    task_config_1 = ConfigTask(node, item,
                            'tc7 first Config task for item 2b',
                            'tc7_res_2b_first', 'tc7_title_2b_first')
                    task_config_2 = ConfigTask(node, item,
                            'tc7 second Config task for item 2b',
                            'tc7_res_2b_second', 'tc7_title_2b_second')
                    tasks.extend([task_config_1, task_config_2])
        return tasks

    def _cb(self, api):
        pass

    def _cb1(self, api):
        pass

    def _cb2(self, api):
        pass
