##############################################################################
# COPYRIGHT Ericsson AB 2013
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################

import json

from litp.core.litp_logging import LitpLogger
from litp.core.model_item import ModelItem
from litp.core.model_item import CollectionItem
from litp.core.model_item import RefCollectionItem
from litp.core.constants import TASK_SUCCESS
from litp.core.constants import MODEL_SERIALISATION_TYPES
from litp.core.constants import LIVE_MODEL
from litp.core.constants import LAST_SUCCESSFUL_PLAN_MODEL
from litp.core.constants import SNAPSHOT_PLAN_MODEL
from litp.core.task import ConfigTask
from litp.core.task import CallbackTask
from litp.core.task import RemoteExecutionTask
from litp.core.task import CleanupTask
from litp.core.plan import Plan, SnapshotPlan
from litp.core.model_manager import QueryItem, ModelManagerException
from litp.core.future_property_value import FuturePropertyValue
from litp.core.exceptions import ModelItemContainerException
from litp.core.persisted_task import PersistedTask
from litp.core.extension_info import ExtensionInfo
from litp.core.plugin_info import PluginInfo
from litp.data.constants import CURRENT_PLAN_ID
from litp.data.constants import LAST_SUCCESSFUL_PLAN_MODEL_ID

log = LitpLogger()


class ModelItemContainer(object):
    """Model Item Container class"""
    def __init__(self, model_manager, plugin_manager, execution_manager):
        """Defines a model container

        :param model_manager: ModelManager instance.
        :type  model_manager: ModelManager
        :param plugin_manager: PluginManager instance.
        :type  plugin_manager: PluginManager
        """
        self.class_picklers = {
            'set': self._pickle_set,
            'ModelItem': self._pickle_model_item,
            'CollectionItem': self._pickle_collection_item,
            'RefCollectionItem': self._pickle_ref_collection_item,
            'Plan': self._pickle_plan,
            'SnapshotPlan': self._pickle_plan,
            'ConfigTask': self._pickle_config_task,
            'CallbackTask': self._pickle_callback_task,
            'RemoteExecutionTask': self._pickle_remote_execution_task,
            'CleanupTask': self._pickle_cleanup_task,
            'FuturePropertyValue': self._pickle_future_property_value
        }
        self.class_unpicklers = {
            'set': self._unpickle_set,
            'ModelItem': self._unpickle_model_item,
            'CollectionItem': self._unpickle_collection_item,
            'RefCollectionItem': self._unpickle_ref_collection_item,
            'Plan': self._unpickle_plan,
            'SnapshotPlan': self._unpickle_plan,

            # kept for compatibility reasons:
            'OrderedPhase': self._unpickle_ordered_phase,

            'ConfigTask': self._unpickle_config_task,
            'CallbackTask': self._unpickle_callback_task,
            'RemoteExecutionTask': self._unpickle_remote_execution_task,
            'CleanupTask': self._unpickle_cleanup_task,
            'FuturePropertyValue': self._unpickle_future_property_value
        }
        self.model_manager = model_manager
        self.plugin_manager = plugin_manager
        self.execution_manager = execution_manager
        self.valid_plan = True

    @property
    def data_manager(self):
        return self.model_manager._data_manager

    def serialize(self):
        """
        This method serializes objects by pickling objects to a JSON format
        A JSON formatted string is returned

        :returns: str
        """

        # model integrity check
#        log.trace.debug("ModelContainer.serialize()")
#        for item in self.model_manager.query_model():
#            vpath = item.vpath
#            if vpath == "/":
#                continue
#            if not item.parent_vpath:
#                log.trace.warning(
#                    "LITPCDS-5382: no parent specified for item: %s", vpath)
#                continue
#            l = vpath.strip("/").rsplit("/", 1)
#            if len(l) == 1:
#                parent_vpath = ""
#            else:
#                parent_vpath = l[0]
#            parent_vpath = "/" + parent_vpath
#            if not self.model_manager.has_item(parent_vpath):
#                log.trace.warning(
#                    "LITPCDS-5382: no parent item exists for item: %s", vpath)

        #log.trace.debug("ModelContainer.serialize()")

        self.data_manager.session.flush()

        items = {}
        for item in self.model_manager.query_model():
            items[item.vpath] = item

        if self.execution_manager:
            data = {
                'items': items,
                'plugins': self.plugin_manager.get_plugin_info(),
                'extensions': self.plugin_manager.get_extension_info(),
                'plan': self.execution_manager.plan,
                'puppet_manager': {
                    'node_tasks':
                        self.execution_manager.puppet_manager.node_tasks,
                },
            }
        else:
            data = {
                'items': items,
                'plugins': self.plugin_manager.get_plugin_info(),
                'extensions': self.plugin_manager.get_extension_info(),
                'plan': {},
                'puppet_manager': {
                    'node_tasks': {},
                },
            }
        ret = self._do_pickling(data)
        return ret

    def do_unpickling(self, json_litp_data, model_type=LIVE_MODEL):
        """
        This method takes a JSON formatted string as input and loads it into
        the model manager.

        :param json_litp_data: A JSON dictionary
        :type  json_litp_data: dict
        """
        #log.trace.debug("ModelContainer.do_unpickling()")
        # create attributes before actual unpickling
        # pylint: disable=W0201
        # alternative would be to have a separate class holding these two
        # in its state
        if model_type not in MODEL_SERIALISATION_TYPES:
            raise ValueError()

        self._unresolved_task_dependencies = {}
        self._unpickled_config_tasks = {}

        data = self._do_unpickling(json_litp_data, model_type)

        # remove the attributes as they aren't necessary throughout the
        # lifetime of ModelContainer
        del self._unresolved_task_dependencies
        del self._unpickled_config_tasks
        return data

    def _plugin_or_extension_change(self, data):
        """Compare plugins and extensions in last known config to filesystem.

        If a plugin or extension has been added, removed or it's version number
        changed, return True. Otherwise return False.
        """
        if (
            sorted(data['plugins']) == sorted(
                self.plugin_manager.get_plugin_info()) and
            sorted(data['extensions']) == sorted(
                self.plugin_manager.get_extension_info())
            ):
            return False
        return True

    def _populate_model(self, items):
        model_items = json.loads(json.dumps(items),
            object_hook=self._unpickle_callback)
        model_id = self.data_manager.model._model_id

        for vpath, item in sorted(model_items.iteritems()):
            parent_vpath, item_id = \
                self.model_manager.split_path(vpath)
            item._item_id = item_id
            item._parent_vpath = parent_vpath

            if item._parent_vpath is None:
                item._vpath = "/"
            elif item._parent_vpath == "/":
                item._vpath = item._parent_vpath + item._item_id
            else:
                item._vpath = item._parent_vpath + "/" + item._item_id

            item._model_id = model_id

            self.data_manager.model.add(item)

    def _do_unpickling(self, data, model_type):
        self._populate_model(data["items"])
        if model_type != SNAPSHOT_PLAN_MODEL:
            self._populate_extensions(data["extensions"], model_type)

        if not self.execution_manager:
            return data

        plan = json.loads(json.dumps(data['plan']),
            object_hook=self._unpickle_callback)
        self._populate_plan(plan)

        self._unpickled_config_tasks.clear()

        node_tasks = \
            json.loads(json.dumps(
                data['puppet_manager']['node_tasks']),
                object_hook=self._unpickle_callback)
        self._populate_persisted_tasks(node_tasks)

        self._populate_plugins(data["plugins"])

        return data

    def _prepare_task(self, _task):
        task = self.data_manager.get_task(_task._id)
        if task is None:
            self.data_manager.add_task(_task)
            task = _task
        return task

    def _populate_plan(self, plan):
        if not plan:
            return

        plan._id = CURRENT_PLAN_ID
        plan._phases = [
            [self._prepare_task(task) for task in phase]
            for phase in plan._phases
        ]
        plan.populate_plan_tasks()
        self.data_manager.add_plan(plan)

    def _populate_persisted_tasks(self, node_tasks):
        for hostname, tasks in node_tasks.iteritems():
            tasks = [self._prepare_task(task) for task in tasks]
            for seq_id, task in enumerate(tasks):
                persisted_task = PersistedTask(hostname, task, seq_id)
                self.data_manager.add_persisted_task(persisted_task)

    def _populate_extensions(self, extensions, model_type):
        for d in extensions:
            extension_info = ExtensionInfo(d["name"], d["class"], d["version"])
            if model_type == LAST_SUCCESSFUL_PLAN_MODEL:
                extension_info._model_id = LAST_SUCCESSFUL_PLAN_MODEL_ID
            self.data_manager.add_extension(extension_info)

    def _populate_plugins(self, plugins):
        for d in plugins:
            plugin_info = PluginInfo(d["name"], d["class"], d["version"])
            self.data_manager.add_plugin(plugin_info)

    def _get_callback(self, method_name, plugin_class):
        plugin = self.plugin_manager.get_plugin(plugin_class)
        if not plugin:
            raise ModelItemContainerException(
                "plan contains CallbackTask with unknown plugin: \"%s\"" %
                plugin_class)
        # This happens when refactoring plugins
        if not hasattr(plugin, method_name):
            self.valid_plan = False
            return None
        return getattr(plugin, method_name)

    def _do_pickling(self, data):
        return json.dumps(data, indent=4, default=self._pickle_callback,
                          sort_keys=True)

    def _pickle_callback(self, obj):
        str_class_name = obj.__class__.__name__
        data = self.class_picklers[str_class_name](obj)
        data['__type__'] = str_class_name
        return data

    def _unpickle_callback(self, data):
        if '__type__' in data:
            return self.class_unpicklers[data['__type__']](data)
        else:
            return data

    def _pickle_set(self, obj):
        return {"data": sorted(list(obj))}

    def _unpickle_set(self, obj):
        return set(obj["data"])

    def _pickle_model_item(self, item):
        # Skip views
        static_props = dict(item._properties)
        for prop_name in static_props.keys():
            if callable(static_props[prop_name]):
                del static_props[prop_name]

        static_applied_props = dict(item._applied_properties)
        for prop_name in static_applied_props.keys():
            if callable(static_applied_props[prop_name]):
                del static_applied_props[prop_name]

        return dict(
            item_type_id=item._item_type.item_type_id,
            item_properties=static_props,
            item_status=item._state,
            item_previous_status=item._previous_state,
            item_applied_properties=static_applied_props,
            item_source=item.source_vpath,
            item_app_prop_det=item.applied_properties_determinable,
        )

    def _pickle_collection_item(self, objItem):
        dict_ancestor = self._pickle_model_item(objItem)
        return dict_ancestor

    def _pickle_ref_collection_item(self, objItem):
        dict_ancestor = self._pickle_model_item(objItem)
        return dict_ancestor

    def _get_item_type(self, item_type_id):
        if item_type_id not in self.model_manager.item_types:
            raise ModelItemContainerException(
                "model contains item with unknown type: \"%s\"" %
                item_type_id)
        return self.model_manager.item_types[item_type_id]

    def _unpickle_model_item(self, data):
        item = ModelItem(self.model_manager,
            self._get_item_type(data['item_type_id']), None, None,
            data['item_properties'])
        item._state = data['item_status']
        item._previous_state = data.get('item_previous_status', None)
        item._applied_properties = data['item_applied_properties']
        item.source_vpath = data['item_source']
        if 'item_app_prop_det' in data:
            item.applied_properties_determinable = data['item_app_prop_det']
        else:
            item.applied_properties_determinable = True
        return item

    def _unpickle_collection_item(self, data):
        item = CollectionItem(self.model_manager,
            self._get_item_type(data['item_type_id']), None, None,
            data['item_properties'])
        item._state = data['item_status']
        item._previous_state = data.get('item_previous_status', None)
        item._applied_properties = data['item_applied_properties']
        item.source_vpath = data['item_source']
        return item

    def _unpickle_ref_collection_item(self, data):
        item = RefCollectionItem(self.model_manager,
            self._get_item_type(data['item_type_id']), None, None,
            data['item_properties'])
        item._state = data['item_status']
        item._previous_state = data.get('item_previous_status', None)
        item._applied_properties = data['item_applied_properties']
        item.source_vpath = data['item_source']
        return item

    def _query_by_vpath(self, vpath):
        try:
            return QueryItem(self.model_manager,
                    self.model_manager.query_by_vpath(vpath))
        except ModelManagerException:
            return QueryItem(self.model_manager, vpath)

    def _pickle_plan(self, plan):
        ret = {
            'state': plan.state,
            'phases': plan.phases,
            'is_snapshot_plan': isinstance(plan, SnapshotPlan),
            'has_cleanup_phase': plan.has_cleanup_phase,
        }
        if isinstance(plan, SnapshotPlan):
            ret['snapshot_type'] = plan.snapshot_type

        return ret

    def _unpickle_plan(self, data):
        def _is_snapshot_plan(data):
            # This function is needed due to backward compatibility reasons.
            # has_snapshot_phase was renamed to is_snapshot_plan.
            try:
                return data['is_snapshot_plan']
            except KeyError:
                return data['has_snapshot_phase']

        if _is_snapshot_plan(data):
            plan = SnapshotPlan([], [], [])
            plan.snapshot_type = data['snapshot_type']
        else:
            plan = Plan([], [])
        plan._phases[:] = data['phases']
        plan._state = data['state']
        return plan

    def _unpickle_ordered_phase(self, data):
        return data["task_list"]

    def _pickle_config_task(self, configtask):
        obj = dict(
            node=configtask.node.vpath,
            model_item=configtask.model_item.vpath,
            model_items=sorted([extra_item.vpath for extra_item in
                         configtask.model_items]),
            description=configtask.description,
            call_type=configtask.call_type,
            call_id=configtask.call_id,
            kwargs=configtask.kwargs,
            state=configtask.state,
            group=configtask.group,
            uuid=configtask.uuid,
            persist=configtask.persist,
            # save dependency info used by PuppetManager
            dependency_unique_ids=sorted(list(configtask._requires))
        )
        requires = {"items": [], "tasks": [], "call_type_call_id": []}
        for dependency in configtask.requires:
            if isinstance(dependency, QueryItem):
                requires["items"].append(dependency.vpath)
            elif isinstance(dependency, ConfigTask):
                requires["tasks"].append(dependency.unique_id)
            elif isinstance(dependency, tuple) and len(dependency) == 2:
                requires["call_type_call_id"].append(list(dependency))

        for dependency_list in requires.values():
            dependency_list.sort()
        obj["requires"] = requires
        if configtask.replaces:
            replaces = [list(x) for x in configtask.replaces]
            replaces.sort()
            obj["replaces"] = replaces
        return obj

    def _unpickle_config_task(self, data):
        task = ConfigTask(
            node=self._query_by_vpath(data['node']),
            model_item=self._query_by_vpath(data['model_item']),
            description=data['description'],
            call_type=data['call_type'],
            call_id=data['call_id'],
            **data.get('kwargs', {})
        )
        task.group = data.get('group')
        task.state = data['state']
        # override new uuid created when task constructor was called with
        # the stored value
        task._id = data.get('uuid') or task._id
        # restore dependency info used by PuppetManager
        task._requires = set(data.get('dependency_unique_ids', []))

        replaces = data.get("replaces", [])
        task.replaces = set(
            [(call_type, call_id) for (call_type, call_id) in replaces]
        )

        task.persist = data.get("persist", True)

        # in an upgrade scenario where the current iso does not contain this
        # attr and the upgraded iso does we expect that the unpickled plan will
        # not be run and a new one will be created. Otherwise there is no way
        # to figure out if this is a snapshot task or not.
        task.is_snapshot_task = data.get('is_snapshot_task', False)

        # rebuild extra model items
        for extra_item_vpath in data.get('model_items', []):
            try:
                item = QueryItem(self.model_manager,
                        self.model_manager.query_by_vpath(extra_item_vpath))
                task.model_items.add(item)
            except ModelManagerException:
                msg = ("Unpickling extra model items of ConfigTask "
                        "{0} {1}; item {2} doesn't exist, skipping")
                log.trace.debug(msg.format(
                    task.call_type, task.call_id, extra_item_vpath))

        if task.state != TASK_SUCCESS:
            msg = ("Unpickled ConfigTask {0} {1}; state is not Succeess; "
                    "skipping rebuilding dependencies")
            log.trace.debug(msg.format(task.call_type, task.call_id))
            return task

        if not task.node._model_item:
            msg = ("Unpickled ConfigTask {0} {1}; node doesn't exist; "
                    "skipping rebuilding dependencies")
            log.trace.debug(msg.format(task.call_type, task.call_id))
            return task

        if not task.model_item._model_item:
            msg = ("Unpickled ConfigTask {0} {1}; model item doesn't exist; "
                    "skipping rebuilding dependencies")
            log.trace.debug(msg.format(task.call_type, task.call_id))
            return task

        return self._rebuild_task_requires(task, data)

    def _rebuild_task_requires(self, task, data):
        hostname = task.node.hostname
        key = (hostname, task.unique_id)
        # store the task for the purpose of recreating dependencies of other
        # tasks
        self._unpickled_config_tasks[key] = task

        requires = data.get("requires", {})

        # rebuild call_type/call_id in Task.requires set
        task.requires |= set(tuple(l)
                             for l in requires.get("call_type_call_id", []))

        # rebuild QueryItems in Task.requires set
        for qitem_vpath in requires.get("items", []):
            try:
                # may have been deleted
                qitem = QueryItem(self.model_manager,
                        self.model_manager.query_by_vpath(qitem_vpath))
                task.requires.add(qitem)
            except ModelManagerException:
                pass

        # rebuild Tasks in Task.requires set
        for dep_task_unique_id in requires.get("tasks", []):
            # search task that is the dependency
            dep_key = (hostname, dep_task_unique_id)
            dependency_task = self._unpickled_config_tasks.get(dep_key)
            if dependency_task:
                task.requires.add(dependency_task)
            else:
                # it's impossible to recreate the dependency at this point
                # as the dependency task hasn't been unserialised yet
                # store ref to task for later update
                self._unresolved_task_dependencies.setdefault(
                    dep_key, set()).add(task)

        tasks_to_update = self._unresolved_task_dependencies.get(key, set())
        for to_update in list(tasks_to_update):
            to_update.requires.add(task)
            tasks_to_update.remove(to_update)

        self._unpickled_config_tasks[key] = task
        return task

    def _pickle_callback_task(self, task):
        return dict(
            model_item=task.model_item.vpath,
            model_items=sorted([
                extra_item.vpath for extra_item in task.model_items
            ]),
            description=task.description,
            callback=task.call_type,
            plugin=task.plugin_class,
            plugin_name=task.plugin_name,
            args=task.args,
            kwargs=task.kwargs,
            state=task.state,
            group=task.group,
        )

    def _unpickle_callback_task(self, data):
        task = CallbackTask(
            model_item=self._query_by_vpath(data['model_item']),
            description=data['description'],
            callback=self._get_callback(data['callback'], data['plugin']),
        )
        # in an upgrade scenario where the current iso does not contain this
        # attr and the upgraded iso does we expect that the unpickled plan will
        # not be run and a new one will be created. Otherwise there is no way
        # to figure out if this is a snapshot task or not.
        task.is_snapshot_task = data.get('is_snapshot_task', False)
        task.args = data.get('args', [])
        task.kwargs = data.get('kwargs', {})
        task.state = data['state']
        task.group = data.get('group')
        task.plugin_name = data.get('plugin_name')

        for extra_item_vpath in data.get('model_items', []):
            try:
                item = QueryItem(self.model_manager,
                        self.model_manager.query_by_vpath(extra_item_vpath))
                task.model_items.add(item)
            except ModelManagerException:
                msg = ("Unpickling extra model items of CallbackTask "
                        "{0}; item {1} doesn't exist, skipping")
                log.trace.debug(msg.format(
                    task.callback, extra_item_vpath))
        return task

    def _pickle_remote_execution_task(self, task):
        return dict(
            model_item=task.model_item.vpath,
            model_items=sorted([
                extra_item.vpath for extra_item in task.model_items
            ]),
            description=task.description,
            plugin=task.plugin_class,
            plugin_name=task.plugin_name,
            args=task.args,
            kwargs=task.kwargs,
            state=task.state,
            nodes=[node.vpath for node in task.nodes],
            agent=task.agent,
            action=task.action,
        )

    def _unpickle_remote_execution_task(self, data):
        task = RemoteExecutionTask(
            nodes=[self._query_by_vpath(vpath) for vpath in data['nodes']],
            model_item=self._query_by_vpath(data['model_item']),
            description=data['description'],
            agent=data['agent'],
            action=data['action']
        )
        task.args = data.get('args', [])
        task.kwargs = data.get('kwargs', {})
        task.plugin_name = data.get('plugin_name')
        task.state = data['state']

        for extra_item_vpath in data.get('model_items', []):
            try:
                item = QueryItem(self.model_manager,
                        self.model_manager.query_by_vpath(extra_item_vpath))
                task.model_items.add(item)
            except ModelManagerException:
                msg = ("Unpickling extra model items of RemoteExecutionTask "
                        "{0} {1}; item {2} doesn't exist, skipping")
                log.trace.debug(msg.format(
                    task.agent, task.action, extra_item_vpath))
        return task

    def _pickle_cleanup_task(self, task):
        return dict(
            model_item=task.model_item.vpath,
            state=task.state,
        )

    def _unpickle_cleanup_task(self, data):
        task = CleanupTask(
            model_item=self._query_by_vpath(data['model_item'])
        )
        task.state = data['state']
        return task

    def _pickle_future_property_value(self, future_property_value):
        return dict(item_vpath=future_property_value.query_item.vpath,
                property_name=future_property_value.property_name)

    def _unpickle_future_property_value(self, data):
        future_property_value = FuturePropertyValue(
                self._query_by_vpath(data["item_vpath"]),
                data["property_name"])
        return future_property_value
