from litp.core.task import Task
from litp.core.litp_logging import LitpLogger
from litp.core.exceptions import NodeLockException
from litp.core.model_manager import QueryItem

log = LitpLogger()


class LockTaskCreator(object):
    """ This class is responsible for creating lock and unlock tasks. Once the
    locking tasks are created it's also responsible for updating tasks with
    locking information. If an actual task needs an update/change (to go
    smoothly with locking tasks), it's gets done here as well.

    """
    def __init__(
                 self, model_manager, plugin_manager, plugin_api_context, nodes
                 ):
        self.model_manager = model_manager
        self.plugin_manager = plugin_manager
        self.plugin_api_context = plugin_api_context
        self.nodes = nodes

    def create_lock_tasks(self):
        lock_tasks = {}
        for node_model_item in self.nodes:
            node = self.model_manager.query_by_vpath(node_model_item.vpath)
            for _, plugin in self.plugin_manager.iter_plugins():
                new_lock_tasks = plugin.create_lock_tasks(
                    self.plugin_api_context,
                    QueryItem(self.model_manager, node)
                )
                if new_lock_tasks:
                    self._validate_lock_tasks(new_lock_tasks)
                    new_lock_tasks[0]._locked_node = node
                    new_lock_tasks[1]._locked_node = node
                    if node.vpath in lock_tasks:
                        msg = ('Node lock/unlock tasks for node %s '
                               'have already been created.' % node.hostname)
                        log.trace.error(msg)
                        raise NodeLockException(msg)
                    self._mark_tasks(new_lock_tasks)
                    lock_tasks[node.vpath] = tuple(new_lock_tasks)
        return lock_tasks

    def _mark_tasks(self, lock_tasks):
        lock_tasks[0].lock_type = Task.TYPE_LOCK
        lock_tasks[1].lock_type = Task.TYPE_UNLOCK

    def _validate_lock_tasks(self, lock_tasks):
        if not isinstance(lock_tasks, tuple):
            raise NodeLockException(
                'Lock/Unlock tasks must be returned as a tuple')
        if len(lock_tasks) != 2:
            raise NodeLockException(
                'Incorect number of lock tasks returned: %s' %
                len(lock_tasks))
        for task in lock_tasks:
            if not isinstance(task, Task):
                raise NodeLockException(
                    'Lock/Unlock task %s is not an instance of Task' % task)
