import re
import time
import subprocess
import uuid

import litp.core.constants as constants
from litp.core.lazy_property import lazy_property
from litp.core.lazy_property import delete_lazy_properties
from litp.core.litp_logging import LitpLogger
from litp.core.model_manager import QueryItem
from litp.core.model_manager import ModelManagerException
from litp.core.future_property_value import FuturePropertyValue
from litp.core.exceptions import TaskValidationException
from litp.core.exceptions import RemoteExecutionException
from litp.plan_types.deployment_plan import deployment_plan_groups
from litp.data.types import Base as DbBase
from litp.data.types import Task as DbTask
from litp.core.task_query_items import TaskQueryItems
from litp.core.task_replaces import TaskReplaces
from litp.core.task_dependencies import TaskDependencies
from litp.core.task_args import TaskArgs
from litp.core.task_kwargs import TaskKwargs


_BASH_COLOR_REGEXP = re.compile(r"\033\[.*?m")
log = LitpLogger()


def _task_has_future_property_value(task):
    if task._kwargs_serialized is None:
        return False
    for value in task._kwargs_serialized.itervalues():
        if (
            isinstance(value, dict) and
            value.get("__class__") == FuturePropertyValue.__name__
        ):
            return True
    return False


def clean_classname(name):
    """
    Convert a string so that it is acceptable as a puppet class name.
    Valid class names contain lower-case letters, digits and/or underscores,
    and must begin with a lower-case letter.  They can also contain '::', but
    we don't need to use that.  See:

    http://docs.puppetlabs.com/guides/faq.html

    We want different input strings to be guaranteed to give different
    output strings, so this needs to be a one-to-one mapping.

    So, we replace:
        1) Any invalid character with "_xx" where "xx" is the hex value
           of the character (using hex digits [0-9a-f], and not [A-F]).
        2) Any existing "_" with "__".

    :param str name: The string to be converted to a valid Puppet class name
    :return A valid Puppet class name derived from `name`
    :rtype str
    """
    return ''.join(s if s in 'abcdefghijklmnopqrstuvwxyz0123456789_'
                   else '_%02x' % ord(s)
                   for s in name.replace('_', '__'))


def get_query_item(model_manager, vpath):
    item = model_manager.query_by_vpath(vpath)
    return QueryItem(model_manager, item)


def get_task_node(task):
    '''
    Returns the node (or MS) the task will be run on for sorting purposes

    :rtype: :class:`litp.core.model_manager.QueryItem`
    '''

    try:
        return task._task_node
    except AttributeError:
        if isinstance(task, ConfigTask):
            task_node = task.get_node()
        elif isinstance(task, RemoteExecutionTask):
            task_node = iter(task.nodes).next()
        elif isinstance(task, CallbackTask):
            task_node = task.get_node_for_model_item()
        elif isinstance(task, CleanupTask):
            task_node = task.model_item.query_by_vpath('/ms')
        else:
            raise ValueError("unknown task type: %s" % type(task))
        task._task_node = task_node
        return task_node


def get_task_model_item_node(task):
    '''
    Returns the node (or MS) under which the task's model item exists in the
    model. If no suitable node can be found (eg. if the item is under
    ``/infrastructure``), then the MS is used.

    :rtype: :class:`litp.core.model_manager.QueryItem`
    '''

    try:
        return task._model_item_node
    except AttributeError:
        mitem = task.model_item
        task_model_item_node = mitem.get_node() or mitem.get_ms()
        task._model_item_node = task_model_item_node
        return task_model_item_node


def can_have_dependency_for_validation(task1, task2):
    task1_node = get_task_node(task1)
    task2_node = get_task_node(task2)
    task_nodes_equal = \
        (task1_node and task1_node.vpath) == (task2_node and task2_node.vpath)
    if task1_node is not None and task2_node is not None \
            and not task_nodes_equal:
        return False
    ms_extended_group = deployment_plan_groups.MS_GROUP
    if not task_nodes_equal and (
        task1.group not in ms_extended_group
            or task2.group not in ms_extended_group):
        return False
    task1_item_node = get_task_model_item_node(task1)
    task2_item_node = get_task_model_item_node(task2)
    if task1_item_node is None or task2_item_node is None \
            or task1_item_node.vpath == task2_item_node.vpath:
        return True
    return False


def can_have_dependency(task1, task2):

    def task_requires_task(task1, task2):
        return task2 in task1.requires

    def task_requires_ConfigTask(task1, task2):
        return isinstance(task2, ConfigTask) and \
            (task2.call_type, task2.call_id) in task1.requires

    def task_requires_model_item(task1, task2):
        return task2.model_item in task1.requires

    if task1.is_deconfigure() != task2.is_deconfigure():
        if any((task_requires_task(task1, task2),
                task_requires_ConfigTask(task1, task2),
                task_requires_model_item(task1, task2))):
            log.trace.warning('The dependency between {task1_is_deconfig} '
                'task "{task1}" for {task1_model_item} '
                '"{task1_model_item_name}" '
                'and {task2_is_deconfig} task '
                '"{task2}" for {task2_model_item} '
                '"{task2_model_item_name}" is deprecated '
                'and will be ignored. This dependency '
                'was created in: {plugin}'.format(
                    plugin=task1.plugin_name,
                    task1=task1.description,
                    task1_model_item=task1.model_item.item_type_id,
                    task1_is_deconfig="deconfigure" if task1.is_deconfigure() \
                    else "configure",
                    task1_model_item_name=task1.model_item.item_id,
                    task2=task2.description,
                    task2_model_item=task2.model_item.item_type_id,
                    task2_is_deconfig="deconfigure" if task2.is_deconfigure() \
                    else "configure",
                    task2_model_item_name=task2.model_item.item_id)
                    )
        return False
    return can_have_dependency_for_validation(task1, task2)


class Task(DbTask, DbBase):
    # pylint: disable=no-member,attribute-defined-outside-init
    TYPE_LOCK = "type_lock"
    TYPE_UNLOCK = "type_unlock"
    TYPE_OTHER = "type_other"

    def __init__(self, model_item, description, tag_name=None):
        """
        :param model_item: The LITP Item that will be affected by the task
        :type model_item: litp.core.model_manager.QueryItem

        :param str description: string that will be used in task reporting
        self.model_item = model_item
        self.description = description

        """

        self._id = str(uuid.uuid4())
        self.model_item = model_item
        self.description = description
        self.tag_name = tag_name
        self.state = constants.TASK_INITIAL
        self.lock_type = Task.TYPE_OTHER
        self._locked_node_item = None
        self.model_items = set()
        self.requires = set()
        self.group = None

        self._init_attributes()

    def _init_attributes(self):
        self._dependency_type = {}
        self._initialized = True
        self.plugin_name = None

        if hasattr(self, "_hash"):
            del self._hash

    def _has_initialized(self):
        return getattr(self, "_initialized", False)

    def initialize_from_db(self, data_manager, model_manager):
        self._data_manager = data_manager
        self._model_manager = model_manager

        delete_lazy_properties(self)

        if self._has_initialized():
            return

        self._init_attributes()

    def _eq_dependencies(self, rhs):
        if self._has_initialized():
            return self._dependencies == rhs._dependencies
        return self._dependencies_serialized == rhs._dependencies_serialized

    def _get_query_item(self, vpath):
        return get_query_item(self._model_manager, vpath)

    @lazy_property
    def _model_item(self):  # pylint: disable=method-hidden
        try:
            item = self._get_query_item(self._model_item_vpath)
        except ModelManagerException:
            item = None
        return item

    @lazy_property
    def _model_items(self):  # pylint: disable=method-hidden
        return TaskQueryItems.deserialize(
            lambda: self._model_items_vpaths, self._model_manager)

    @lazy_property
    def _dependencies(self):  # pylint: disable=method-hidden
        return TaskDependencies.deserialize(
            lambda: self._dependencies_serialized,
            self._data_manager, self._model_manager)

    @lazy_property
    def _locked_node_item(self):  # pylint: disable=method-hidden
        try:
            item = self._model_manager.query_by_vpath(self._locked_node_vpath)
        except ModelManagerException:
            item = None
        return item

    def _copy_task_attributes(self, task):
        task.lock_type = self.lock_type
        task._locked_node_vpath = self._locked_node_vpath
        task.group = self.group

    def copy(self):
        task = Task(self.model_item, self.description, self.tag_name)
        self._copy_task_attributes(task)
        return task

    @property
    def model_item(self):
        if self._model_item is None:
            return self._model_item_vpath
        return self._model_item

    @model_item.setter
    def model_item(self, model_item):
        self._model_item = model_item
        self._model_item_vpath = model_item.vpath

    @property
    def model_items(self):
        return self._model_items

    @model_items.setter
    def model_items(self, value):
        self._model_items_vpaths = set()
        self._model_items = TaskQueryItems(
            lambda: self._model_items_vpaths, value)

    @property
    def requires(self):
        return self._dependencies

    @requires.setter
    def requires(self, value):
        self._dependencies_serialized = set()
        self._dependencies = TaskDependencies(
            lambda: self._dependencies_serialized, value)

    @property
    def _locked_node(self):
        if self._locked_node_item is None:
            return self._locked_node_vpath
        return self._locked_node_item

    @_locked_node.setter
    def _locked_node(self, node):
        self._locked_node_item = node
        self._locked_node_vpath = node.vpath if node else None

    def is_deconfigure(self):
        return (self.model_item.is_for_removal() and
                self.state != constants.TASK_SUCCESS)

    @property
    def all_model_items(self):
        items = set(self.model_items)
        if self._model_item:
            items.add(self._model_item)
        return items

    def all_model_items_determinable(self):
        return all(associated_item.applied_properties_determinable for
            associated_item in self.all_model_items)

    def __eq__(self, rhs):
        return rhs and type(rhs) is type(self) and \
            self._model_item_vpath == rhs._model_item_vpath

    def get_model_item(self):
        return self.model_item

    @property
    def item_vpath(self):
        """
        returns the vpath of the model item
        with which this task is associated
        """
        return self._model_item_vpath

    def has_run(self):
        """ returns boolean whether task has been run"""
        return self.state not in [constants.TASK_INITIAL,
                                  constants.TASK_RUNNING]

    def format_parameters(self):
        raise NotImplementedError

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def task_id(self):
        raise NotImplementedError

    def _check_args(self, var):
        if type(var) in set([int, str, unicode, float, bool, type(None)]):
            return
        if isinstance(var, FuturePropertyValue):
            if var.is_view():
                self._check_args(var.value)
                return
            if var.is_updatable_plugin():
                self._check_args(var.value)
                return
        if type(var) in set([TaskArgs, list, tuple, set]):
            for value in var:
                self._check_args(value)
            return
        if type(var) in set([TaskKwargs, dict]):
            for value in var.itervalues():
                self._check_args(value)
            return
        raise TypeError(
            "Invalid task argument type: %s" % (type(var)))


class ConfigTask(Task):
    # pylint: disable=attribute-defined-outside-init
    """
    The ConfigTask class defines tasks for execution by LITP as puppet
    configuration. ConfigTasks are executed by puppet.
    """

    def __init__(self, node, model_item, description, call_type, call_id,
                 **kwargs):
        r"""
        :param node: The LITP node that the task will configure
        :type node: :class:`~litp.core.model_manager.QueryItem`

        :param model_item: The LITP Item that will be affected by the task
        :type model_item: :class:`~litp.core.model_manager.QueryItem`

        :param description: string that will be used in task reporting
        :type description: str

        :param call_type: The name of the Puppet resource type used by
            this :class:`ConfigTask`
        :type call_type: str

        :param call_id: A unique identifier for this :class:`ConfigTask`.
            ``call_id`` is meant to be unique for :class:`ConfigTask` objects
            of a given ``call_type`` on a given node.
        :type call_id: str

        :param \**kwargs: Optional key, value dictionary for the attributes of
            the Puppet resource that will effect this :class:`ConfigTask`
        """

        tag_name = kwargs.pop('tag_name', None)
        self.node = node
        self.call_type = call_type
        self.call_id = call_id
        self._unique_id = clean_classname(
            "%s_%s_%s" % (self._node_hostname, self._call_type, self._call_id))

        self.kwargs = kwargs
        self.replaces = set()
        self._requires = set()
        self.persist = True

        super(ConfigTask, self).__init__(
            model_item, description, tag_name=tag_name
        )

    def initialize_from_db(self, data_manager, model_manager):
        super(ConfigTask, self).initialize_from_db(
            data_manager, model_manager)

        if self._has_initialized():
            return

    @lazy_property
    def _node(self):  # pylint: disable=method-hidden
        try:
            node = self._get_query_item(self._node_vpath)
        except ModelManagerException:
            node = None
        return node

    @lazy_property
    def _kwargs(self):  # pylint: disable=method-hidden
        return TaskKwargs.deserialize(
            lambda: self._kwargs_serialized, self._model_manager)

    @lazy_property
    def _replaces(self):  # pylint: disable=method-hidden
        return TaskReplaces.deserialize(
            lambda: self._replaces_serialized)

    def copy(self):
        task = ConfigTask(
            self.node, self.model_item, self.description,
            self.call_type, self.call_id,
            tag_name=self.tag_name, **self.kwargs)
        self._copy_task_attributes(task)
        return task

    def is_deconfigure(self):
        return ((self.model_item.is_for_removal() or self.persist == False)
               and self.state != constants.TASK_SUCCESS)

    def __eq__(self, rhs):
        return rhs and (
            type(rhs) is ConfigTask and
            self._node_vpath == rhs._node_vpath and
            self._model_item_vpath == rhs._model_item_vpath and
            self.call_type == rhs.call_type and
            self.call_id == rhs.call_id and
            self._kwargs_serialized == rhs._kwargs_serialized and
            self._eq_dependencies(rhs) and
            not _task_has_future_property_value(self) and
            not _task_has_future_property_value(rhs) and
            self.persist == rhs.persist
        )

    def __hash__(self):
        if not hasattr(self, "_hash"):
            self._hash = hash((
                type(self),
                self._node_vpath,
                self._model_item_vpath,
                self._call_type,
                self._call_id,))
        return self._hash

    def __repr__(self):
        return "<ConfigTask %s %s - %s: %s [%s]; id=%s, req_id=%s>" % (
            self._node_hostname, self._model_item_vpath,
            self.call_type, self.call_id,
            self.state, self.unique_id, self._requires)

    @property
    def _node_hostname(self):
        if self._node is None or self._node._model_item is None:
            return "unknown (vpath=%s)" % self._node_vpath
        return self._node.hostname

    @property
    def uuid(self):
        return self._id

    @property
    def node(self):
        if self._node is None:
            return self._node_vpath
        return self._node

    @node.setter
    def node(self, node):
        self._node = node
        self._node_vpath = node.vpath

    @property
    def replaces(self):
        return self._replaces

    @replaces.setter
    def replaces(self, value):
        self._replaces_serialized = set()
        self._replaces = TaskReplaces(lambda: self._replaces_serialized, value)

    @property
    def _requires(self):
        return self._dependency_unique_ids

    @_requires.setter
    def _requires(self, value):
        self._dependency_unique_ids = value

    @property
    def call_type(self):
        return self._call_type

    @call_type.setter
    def call_type(self, value):
        self._call_type = value

    @property
    def call_id(self):
        return self._call_id

    @call_id.setter
    def call_id(self, value):
        self._call_id = value

    @property
    def kwargs(self):
        return self._kwargs

    @kwargs.setter
    def kwargs(self, value):
        self._kwargs_serialized = {}
        self._kwargs = TaskKwargs(lambda: self._kwargs_serialized, value)

    # Candidate for @property
    def get_node(self):
        """ returns the node with which this task is associated"""
        return self.node

    @property
    def task_id(self):
        return self.unique_id + "_" + str(hash(self))

    def format_parameters(self):
        return {
            "call_id": self.call_id,
            "call_type": self.call_type,
            "description": self.description,
            "kwargs": str(self.kwargs or ""),
            "model_item": {
                'type': self.model_item.item_type.item_type_id,
                'id': self.model_item.item_id,
                "uri": "/item-types/%s" %
                self.model_item.item_type.item_type_id
            },
            "node": {
                'type': self.
                    node.item_type.item_type_id,
                'id': self.node.item_id,
                "uri": "/item-types/%s" %
                self.node.item_type.item_type_id
            }
        }

    def validate(self):
        log.trace.debug("Validating task: %s", self)
        self._check_args(self.kwargs)


class CallbackTask(Task):
    # pylint: disable=attribute-defined-outside-init
    """
    The CallbackTask class defines tasks for execution by LITP as callbacks to
    the referenced methods in the plug-in module providing the task.
    Callback tasks are executed by the execution manager directly.
    """

    def __init__(self, model_item, description, callback, *args, **kwargs):
        r"""
        :param model_item: The LITP Item that will be affected by the task
        :type model_item: :class:`~litp.core.model_manager.QueryItem`

        :param description: string that will be used in task reporting
        :type description: str

        :param callback: The plug-in function to be executed
        :type callback: instancemethod

        :param args: The argument list to be provided to the callback function
        :type args:

        :param \**kwargs: Optional key, value args for the callback function
        :type kwargs:

        """

        tag_name = kwargs.pop('tag_name', None)
        self.callback = callback
        self.args = args
        self.kwargs = kwargs
        self._unique_id = clean_classname("%s_%s_%s" % (
            self._model_item_vpath, self._callback_name,
            str(hash(str(self.args) + str(self.kwargs)))))

        super(CallbackTask, self).__init__(
            model_item, description, tag_name=tag_name
        )

    def initialize_from_db(self, data_manager, model_manager):
        super(CallbackTask, self).initialize_from_db(
            data_manager, model_manager)

        if self._has_initialized():
            return

    @lazy_property
    def _args(self):  # pylint: disable=method-hidden
        return TaskArgs.deserialize(
            lambda: self._args_serialized, self._model_manager)

    @lazy_property
    def _kwargs(self):  # pylint: disable=method-hidden
        return TaskKwargs.deserialize(
            lambda: self._kwargs_serialized, self._model_manager)

    def copy(self):
        task = CallbackTask(
            self.model_item, self.description, self.callback,
            *self.args, **self.kwargs)
        self._copy_task_attributes(task)
        return task

    def __eq__(self, rhs):
        return rhs and type(rhs) is type(self) and \
            self._model_item_vpath == rhs._model_item_vpath and \
            self._plugin_class == rhs._plugin_class and \
            self._callback_name == rhs._callback_name and \
            self._args_serialized == rhs._args_serialized and \
            self._kwargs_serialized == rhs._kwargs_serialized and \
            self._eq_dependencies(rhs)

    def __hash__(self):
        if not hasattr(self, "_hash"):
            self._hash = hash((
                str(type(self)),
                self._model_item_vpath,
                self._plugin_class,
                self._callback_name,
                str(self._get_args_for_hash()),
                str(self._get_kwargs_for_hash())))
        return self._hash

    def __repr__(self):
        return "<%s %s - %s: %s [%s]>" % \
            (self.__class__.__name__,
             self.item_vpath,
             self._callback_name,
             tuple(self._args) or "",
             self.state)

    def _get_args_for_hash(self):
        return (
            self._args_serialized
            if self._args_serialized is not None
            else []
        )

    def _get_kwargs_for_hash(self):
        return (
            sorted([
                (k, v) for k, v in self._kwargs_serialized.iteritems()])
            if self._kwargs_serialized is not None
            else []
        )

    @property
    def args(self):
        return tuple(self._args)

    @args.setter
    def args(self, value):
        self._args_serialized = []
        self._args = TaskArgs(lambda: self._args_serialized, value)

    @property
    def kwargs(self):
        return self._kwargs

    @kwargs.setter
    def kwargs(self, value):
        self._kwargs_serialized = {}
        self._kwargs = TaskKwargs(lambda: self._kwargs_serialized, value)

    @property
    def call_type(self):
        """ Deprecated. """
        return self._callback_name

    @property
    def callback(self):
        return self._callback

    @callback.setter
    def callback(self, value):
        self._callback = value
        if value:
            try:
                self._callback_name = value.__name__
            except AttributeError:
                # TODO: remove! required for some UTs
                self._callback_name = str(value)
            if hasattr(value, "im_self"):
                cls = value.im_self.__class__
                self._plugin_class = "%s.%s" % (cls.__module__, cls.__name__)
            else:
                # TODO: remove! required for some UTS
                self._plugin_class = "%s.%s" % (None, str(value))
        else:
            # TODO: remove! required for some UTs
            self._callback_name = None
            self._plugin_class = None

    @property
    def plugin_class(self):
        return self._plugin_class

    @property
    def task_id(self):
        return self.unique_id + "_" + str(hash(self))

    def get_node_for_model_item(self):
        return self.model_item.get_node() or self.model_item.get_ms()

    def format_parameters(self):
        return {
            "call_type": self.call_type,
            "description": self.description,
            "kwargs": str(self.kwargs or ""),
            "model_item": {
                'type': self.model_item.item_type.item_type_id,
                'id': self.model_item.item_id,
                "uri": "/item-types/%s" %
                self.model_item.item_type.item_type_id
            }
        }

    def validate(self):
        log.trace.debug("Validating task: %s", self)
        self._check_args(self.args)
        self._check_args(self.kwargs)


class RemoteExecutionTask(CallbackTask):
    # pylint: disable=attribute-defined-outside-init
    def __init__(self, nodes, model_item, description, agent, action,
                 **kwargs):
        r"""
        :param nodes: The list of nodes (management server and/or peer
                      server(s)) where the task will be run
        :type nodes: list of :class:`~litp.core.model_manager.QueryItem`

        :param model_item: The LITP model item that will be affected by the
                           task
        :type model_item: :class:`~litp.core.model_manager.QueryItem`

        :param description: The string that will be used in task reporting
        :type description: str

        :param agent: The MCollective agent to be used
        :type agent: str

        :param action: The MCollective agent action to be used
        :type action: str

        :param \**kwargs: Optional keyword arguments for the MCollective
                         agent action
        """

        # Use copy of nodes, not the provided list.
        self.nodes = set(nodes)
        self.agent = agent
        self.action = action

        super(RemoteExecutionTask, self).__init__(
            model_item, description, self._mco_callback, **kwargs)

    def initialize_from_db(self, data_manager, model_manager):
        super(RemoteExecutionTask, self).initialize_from_db(
            data_manager, model_manager)

        if self._has_initialized():
            return

    @lazy_property
    def _nodes(self):  # pylint: disable=method-hidden
        return TaskQueryItems.deserialize(
            lambda: self._nodes_vpaths, self._model_manager)

    def copy(self):
        task = RemoteExecutionTask(
            self.nodes, self.model_item, self.description,
            self.agent, self.action, **self.kwargs)
        self._copy_task_attributes(task)
        return task

    @property
    def nodes(self):
        return self._nodes

    @nodes.setter
    def nodes(self, value):
        self._nodes_vpaths = set()
        self._nodes = TaskQueryItems(lambda: self._nodes_vpaths, value)

    def __hash__(self):
        if not hasattr(self, "_hash"):
            self._hash = hash((
                self._model_item_vpath,
                str(sorted(self._nodes_vpaths)) if self._nodes_vpaths else "",
                self.agent,
                self.action,
                str(self._get_args_for_hash()),
                str(self._get_kwargs_for_hash())))
        return self._hash

    def validate(self):
        super(RemoteExecutionTask, self).validate()
        if not len(self.nodes):
            raise ValueError(
                "At least one node or ms must be specified")
        for node in self.nodes:
            if not isinstance(node, QueryItem):
                raise TypeError(
                    "node should be a QueryItem instance, "
                    "got %s instead" % type(node))
            if node.item_type.item_type_id not in set(["node", "ms"]):
                raise ValueError(
                    "Invalid node or ms specified: %s" % node)

    def __repr__(self):
        return "<%s %s - %s: %s [%s]>" % \
            (self.__class__.__name__,
             [node.hostname if node.is_node() else node
              for node in self.nodes],
             self.item_vpath,
             str(tuple(self.args) or ""),
             self.state)

    def __eq__(self, rhs):
        return (
            rhs and type(rhs) is type(self) and
            self._model_item_vpath == rhs._model_item_vpath and
            self.agent == rhs.agent and self.action == rhs.action and
            self._args_serialized == rhs._args_serialized and
            self._kwargs_serialized == rhs._kwargs_serialized
        )

    def _generate_command_args(self, **kwargs):
        # mco command
        command_args = [
            "mco", "rpc", "--no-progress", str(self.agent), str(self.action)]

        # mco command arguments
        for key, val in kwargs.iteritems():
            command_args.append("=".join([str(key).strip(), str(val).strip()]))

        # mco command filter
        for node in self.nodes:
            command_args.extend(["-I", str(node.hostname)])

        return command_args

    def _remove_non_printing_escape_sequences(self, s):
        return _BASH_COLOR_REGEXP.sub("", s)

    def _run_process(self, callback_api, command_args):
        log.trace.debug("Running process %s", command_args)
        process = subprocess.Popen(command_args, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT)
        while process.poll() is None and callback_api.is_running():
            time.sleep(0.5)
        if callback_api.is_running():
            return self._communicate(process, command_args)
        else:
            return

    def _communicate(self, process, command_args):
        output, _ = process.communicate()
        for line in output.split("\n"):
            log.trace.debug(self._remove_non_printing_escape_sequences(line))
        ret = process.returncode
        if ret:
            log.trace.error("Error running %s, return code %s",
                            command_args, ret)
        else:
            log.trace.debug("Running %s finished successfully", command_args)
        return ret

    def _mco_callback(self, callback_api, **kwargs):
        command_args = self._generate_command_args(**kwargs)
        ret = self._run_process(callback_api, command_args)
        if ret:
            raise RemoteExecutionException("error running RemoteExecutionTask")


class CleanupTask(Task):
    def __init__(self, model_item):
        super(CleanupTask, self).__init__(model_item, 'Remove Item')
        self._unique_id = clean_classname("%s_%s" % (
            self.item_vpath, self.call_type))

    def __repr__(self):
        return "<%s %s - [%s]>" % (
            self.__class__.__name__,
            self.model_item,
            self.state)

    @property
    def task_id(self):
        return clean_classname(self.unique_id + "_" + str(hash(
            self._model_item_vpath)))

    @property
    def call_type(self):
        return 'cleanup'

    def format_parameters(self):
        return {
            "description": self.description,
            "model_item": {
                'type': self.model_item.item_type.item_type_id,
                'id': self.model_item.item_id,
                "uri": "/item-types/%s" %
                self.model_item.item_type.item_type_id
            },
        }


class OrderedTaskList(object):
    """
    The OrderedTaskList class defines a task list that contains ordered
    instances of ConfigTask and/or CallbackTask. The tasks are executed in the
    given order and are not topologically sorted.

    **Example Usage:**

    .. code-block:: python

        OrderedTaskList(node.os, [
            ConfigTask(
                node, node.os, "", "dummy_task_3_1", "3_1"),
            ConfigTask(
                node, node.os, "", "dummy_task_3_2", "3_2"),
            CallbackTask(
                node.os, "dummy_task_4_1", self._mock_function, "4_1"),
            ConfigTask(
                node, node.os, "", "dummy_task_5_1", "5_1"),
            ConfigTask(
                node, node.os, "", "dummy_task_5_2", "5_2"),
        ]),

    Please note that although each task within a list takes a ``model_item`` as
    an argument, it is overriden by ``model_item`` argument passed to
    OrderedTaskList.
    """

    def __init__(self, model_item, task_list):
        """
        :param model_item: The LITP Item that will be affected by the task
        :type model_item: litp.core.model_manager.QueryItem
        :param task_list: An ordered list of tasks
        :type task_list: list

        """

        self.model_item = model_item
        self.task_list = task_list
        self.args = []
        self.kwargs = {}

        self._node = False

    def __repr__(self):
        return "<OrderedTaskList %s %s>" % (self.model_item, self.task_list)

    def _validate_task_list(self, task_list):
        for i, task in enumerate(task_list):
            try:
                next_task = task_list[i + 1]
            except IndexError:
                break  # no more tasks
            if isinstance(task, OrderedTaskList) \
                    or isinstance(next_task, OrderedTaskList):
                raise TaskValidationException(
                    "Nested OrderedTaskLists are not supported")
            if not can_have_dependency_for_validation(task, next_task):
                raise TaskValidationException(
                    ("OrderedTaskList can only contain tasks for the "
                     "same node. Offending task: {0}").format(next_task))

    def validate(self):
        log.trace.debug("Validating task: %s", self)
        if not len(self.task_list):
            raise TaskValidationException(
                "no tasks specified"
            )
        self._validate_task_list(self.task_list)
        for task in self.task_list:
            task.validate()
