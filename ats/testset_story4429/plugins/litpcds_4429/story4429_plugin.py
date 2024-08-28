from mock import patch
import uuid

from litp.core.plugin import Plugin
from litp.core.task import OrderedTaskList
from litp.core.task import ConfigTask
from litp.core.task import CallbackTask

from litp.core.litp_logging import LitpLogger
log = LitpLogger()


class Story4429Plugin(Plugin):

    def _get_nodes(self, plugin_api_context):

        nodes = [node for node in plugin_api_context.query('node')]
        nodes.extend(plugin_api_context.query('ms'))

        return nodes

    def _get_model_items(self, plugin_api_context):

        model_items = [
            model_item
            for model_item in plugin_api_context.query('story4429')
            if model_item.is_initial()
        ]

        return model_items

    def _get_reference_items(self, node, model_item):

        reference_items = [ref_item
            for ref_item in node.query('story4429')
            if ref_item.get_source().get_vpath() == model_item.get_vpath()
        ]

        return reference_items

    def cb_do_nothing(self, item):
        log.trace.info(item)

    def cb_do_nothing1(self, item):
        log.trace.info(item)

    def cb_do_nothing2(self, item):
        log.trace.info(item)

    def cb_do_nothing3(self, item):
        log.trace.info(item)

    def _get_callback_task(self, item, description, cbnum=None):

        if cbnum:
            if cbnum == '1':
                return CallbackTask(item, description, self.cb_do_nothing)
            elif cbnum == '2':
                return CallbackTask(item, description, self.cb_do_nothing2)
            elif cbnum == '3':
                return CallbackTask(item, description, self.cb_do_nothing3)
        else:
            return CallbackTask(item, description, self.cb_do_nothing)

    def _get_config_task(self, node, item, description):

        unique_id = 'cf_do_nothing_{0}_{1}'.format(
            item.name, str(uuid.uuid4().int)
        )
        return unique_id, \
            ConfigTask(node, item, description, 'notify', unique_id)

    def create_configuration(self, plugin_api_context):
        uuid_patch = patch('uuid.uuid4')
        patched_uuid = uuid_patch.start()
        patched_uuid.side_effect = lambda: uuid.UUID(int=patched_uuid.call_count)

        tasks = list()
        ordered_tasks = list()
        nodes = self._get_nodes(plugin_api_context)
        model_items = self._get_model_items(plugin_api_context)
        for model_item in model_items:
            if model_item.name == 'test_01':
                log.trace.info(
                    'STORY4429: Executing test {0}_n_ordered_task_list_'\
                    'validation'.format(model_item.name)
                )
                for node in nodes:
                    reference_items = self._get_reference_items(
                        node, model_item
                    )
                    for ref_item in reference_items:
                        ordered_tasks.append(
                            self._get_callback_task(
                                ref_item,
                                'CallbackTask() {0}:{1}'.format(
                                    node.hostname, model_item.name
                                )
                            )
                        )
                tasks.append(OrderedTaskList(model_item, ordered_tasks))
            elif model_item.name == 'test_02':
                log.trace.info(
                    'STORY4429: Executing test {0}_p_task_dependencies'.format(
                        model_item.name
                    )
                )
                node = nodes[0]
                taskA = self._get_callback_task(
                    model_item,
                    'CallbackTask() TaskA:{0}:{1}'.format(
                        model_item.name, node.hostname
                    ),
                    '1'
                )
                taskB = self._get_callback_task(
                    model_item,
                    'CallbackTask() TaskB:{0}:{1}'.format(
                        model_item.name, node.hostname
                    ),
                    '2'
                )
                taskA.requires.add(taskB)
                tasks.append(taskA)
                tasks.append(taskB)
            elif model_item.name == 'test_03':
                log.trace.info(
                    'STORY4429: Executing test {0}_n_task_cyclic_'\
                    'dependency'.format(model_item.name)
                )
                node = nodes[0]
                taskA = self._get_callback_task(
                    model_item,
                    'CallbackTask() TaskA:{0}:{1}'.format(
                        model_item.name, node.hostname
                    ),
                    '1'
                )
                taskB = self._get_callback_task(
                    model_item,
                    'CallbackTask() TaskB:{0}:{1}'.format(
                        model_item.name, node.hostname
                    ),
                    '2'
                )
                taskC = self._get_callback_task(
                    model_item,
                    'CallbackTask() TaskC:{0}:{1}'.format(
                        model_item.name, node.hostname
                    ),
                    '3'
                )
                taskA.requires.add(taskB)
                taskB.requires.add(taskC)
                taskC.requires.add(taskA)
                tasks.append(taskA)
                tasks.append(taskB)
                tasks.append(taskC)
            elif model_item.name == 'test_04':
                log.trace.info(
                    'STORY4429: Executing test {0}_n_ordered_task_list_'\
                    'cyclic_dependencies'.format(model_item.name)
                )
                node = nodes[0]
                taskA = self._get_callback_task(
                    model_item,
                    'CallbackTask() TaskA:{0}:{1}'.format(
                        model_item.name, node.hostname
                    ),
                    '1'
                )
                taskB = self._get_callback_task(
                    model_item,
                    'CallbackTask() TaskB:{0}:{1}'.format(
                        model_item.name, node.hostname
                    ),
                    '2'
                )
                taskA.requires.add(taskB)
                tasks.append(OrderedTaskList(model_item, [taskA, taskB]))
            elif model_item.name == 'test_05':
                log.trace.info(
                    'STORY4429: Executing test {0}_p_task_depends_on_ordered'\
                    '_task_list_task'.format(model_item.name)
                )
                node = nodes[0]
                taskA = self._get_callback_task(
                    model_item,
                    'CallbackTask() TaskA:{0}:{1}'.format(
                        model_item.name, node.hostname
                    ),
                    '1'
                )
                taskB = self._get_callback_task(
                    model_item,
                    'CallbackTask() TaskB:{0}:{1}'.format(
                        model_item.name, node.hostname
                    ),
                    '2'
                )
                taskC = self._get_callback_task(
                    model_item,
                    'CallbackTask() TaskC:{0}:{1}'.format(
                        model_item.name, node.hostname
                    ),
                    '3'
                )
                taskA.requires.add(taskC)
                tasks.append(taskA)
                tasks.append(OrderedTaskList(model_item, [taskB, taskC]))
            elif model_item.name == 'test_06':
                log.trace.info(
                    'STORY4429: Executing test {0}_n_task_depends_on_'\
                    '_query_item_diff_node'.format(model_item.name)
                )
                node = nodes[0]
                _, taskA = self._get_config_task(
                    node, model_item,
                    'ConfigTask() TaskA:{0}:{1}'.format(
                        model_item.name, node.hostname
                    )
                )
                node = nodes[1]
                _, taskB = self._get_config_task(
                    node, model_item,
                    'ConfigTask() TaskB:{0}:{1}'.format(
                        model_item.name, node.hostname
                    )
                )
                taskA.requires = set([nodes[1]])
                tasks.append(taskA)
                tasks.append(taskB)
            elif model_item.name == 'test_07':
                log.trace.info(
                    'STORY4429: Executing test {0}_p_task_depends_on_'\
                    '_query_item_call_type_call_id'.format(model_item.name)
                )
                node = nodes[0]
                model_itemB = plugin_api_context.query('story4429-1')[0]
                _, taskA = self._get_config_task(
                    node, model_item,
                    'ConfigTask() TaskA:{0}:{1}'.format(
                        model_item.name, node.hostname
                    )
                )
                unique_idB, taskB = self._get_config_task(
                    node, model_itemB,
                    'ConfigTask() TaskB:{0}:{1}'.format(
                        model_itemB.name, node.hostname
                    )
                )
                ref_itemB = node.query('story4429-1')[0]
                taskA.requires = set([ref_itemB, ('notify', unique_idB)])
                tasks.append(taskA)
                tasks.append(taskB)
            elif model_item.name == 'test_08':
                log.trace.info(
                    'STORY4429: Executing test {0}_p_task_depends_on_'\
                    '_query_item_only'.format(model_item.name)
                )
                node = nodes[0]
                model_itemB = plugin_api_context.query('story4429-1')[0]
                _, taskA = self._get_config_task(
                    node, model_item,
                    'ConfigTask() TaskA:{0}:{1}'.format(
                        model_item.name, node.hostname
                    )
                )
                taskB = self._get_callback_task(
                    model_itemB,
                    'CallbackTask() TaskB:{0}:{1}'.format(
                        model_itemB.name, node.hostname
                    ),
                    '1'
                )
                ref_itemB = node.query('story4429-1')[0]
                taskA.requires = set([ref_itemB])
                tasks.append(taskA)
                tasks.append(taskB)
            elif model_item.name == 'test_09':
                log.trace.info(
                    'STORY4429: Executing test {0}_n_task_depends_on_'\
                    '_call_type_no_call_id'.format(model_item.name)
                )
                node = nodes[0]
                _, taskA = self._get_config_task(
                    node, model_item,
                    'ConfigTask() TaskA:{0}:{1}'.format(
                        model_item.name, node.hostname
                    )
                )
                model_itemB = plugin_api_context.query('story4429-1')[0]
                unique_idB, taskB = self._get_config_task(
                    node, model_item,
                    'ConfigTask() TaskB:{0}:{1}'.format(
                        model_itemB.name, node.hostname
                    )
                )
                ref_itemB = node.query('story4429-1')[0]
                taskA.requires = set([ref_itemB, ('notify', )])
                tasks.append(taskA)
                tasks.append(taskB)
            elif model_item.name == 'test_10':
                log.trace.info(
                    'STORY4429: Executing test {0}_p_task_depends_on_'\
                    '_own_query_item'.format(model_item.name)
                )
                node = nodes[0]
                unique_idA, taskA = self._get_config_task(
                    node, model_item,
                    'ConfigTask() TaskA:{0}:{1}'.format(
                        model_item.name, node.hostname
                    )
                )
                ref_itemA = node.query('story4429')[0]
                taskA.requires = set([ref_itemA, ('notify', unique_idA)])
                tasks.append(taskA)

        return tasks
