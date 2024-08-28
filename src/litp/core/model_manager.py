##############################################################################
# COPYRIGHT Ericsson AB 2013
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################
import re
import logging
from Queue import deque
from collections import OrderedDict
from contextlib import contextmanager

from ConfigParser import SafeConfigParser

from litp.core.base_manager import BaseManager
from litp.core.model_item import ModelItem
from litp.core.model_item import CollectionItem
from litp.core.model_item import RefCollectionItem
from litp.core.model_type import Collection
from litp.core.model_type import RefCollection
from litp.core.model_type import Property
from litp.core.model_type import Child
from litp.core.model_type import Reference
from litp.core.model_type import View
from litp.core.model_type import PropertyType
from litp.core.model_type import ItemType
from litp.core.model_type import PROPERTY_READ
from litp.core.model_type import PROPERTY_WRITE
from litp.core.model_validator import ModelValidator
from litp.core.model_dependency import ModelDependencyHelper
from litp.core.validators import ValidationError
from litp.core.litp_logging import LitpLogger
import litp.core.constants as constants
from litp.core.exceptions import ModelManagerException
from litp.core.exceptions import ViewError


log = LitpLogger()
LITP_LOG_CONF_FILE_PATH = "/etc/litp_logging.conf"


class QueryItem(object):
    """  The result of a query on the Model is a list of QueryItems.
    A QueryItem wraps a ModelItem representing the state and
    properties of the ModelItem to a plugin without exposing the
    actual ModelItem.

    Dot notation can used to access the properties and children of a
    QueryItem, for example a node QueryItem can access its hostname
    property by \"node.hostname\".

    A subsequent query can be performed on a QueryItem to return any
    child items and their properties. e.g. A query on the model
    might return a list of node QueryItems, a subsequent query
    on one of these QueryItems, might return a list of packages for that
    particular node.
    """

    def __init__(self, model_manager, model_item, updatable=False):
        """
        :param model_manager: ModelManager instance.
        :type  model_manager: ModelManager
        :param    model_item: ModelItem to represent or its vpath.
        :type     model_item: ModelItem or str
        :param  dependencies: Copy of ``model_item``'s dependencies.
        :type   dependencies: set
        """
        self._manager = model_manager
        if not isinstance(model_item, (str, unicode)):
            self._model_item = model_item
            self._vpath = model_item.vpath
        else:
            self._model_item = self._manager.get_item(model_item)
            self._vpath = model_item
        self._updatable = updatable
        self._children_cache = None

    @property
    def applied_properties_determinable(self):
        """
        Returns a boolean flag indicating whether all tasks previously involved
        in applying the configuration described by this item have executed
        successfully.

        If set to ``False``, the item's :py:attr:`QueryItem.applied_properties`
        dictionary does not accurately reflect the configuration applied on the
        deployment.

        :returns: The item's ``applied_properties_determinable`` flag
        :rtype:   bool
        """
        return self._model_item.applied_properties_determinable

    @property
    def parent(self):
        """
        Return the parent item of this item.

        :returns: The parent item of this item.
        :rtype:   :class:`litp.core.model_manager.QueryItem` or None
        """
        return self.get_parent()

    def __repr__(self):
        return "<QueryItem %s [%s]>" % (self.vpath, self.get_state())

    def __eq__(self, rhs):
        return (rhs and type(rhs) is QueryItem and
                self._model_item == rhs._model_item)

    def __hash__(self):
        return hash(self.vpath)

    def __cmp__(self, rhs):
        if not rhs:
            return 1
        return cmp(self.vpath, rhs.vpath)

    def __len__(self):
        return len(self._model_item)

    def __nonzero__(self):
        return True

    def __iter__(self):
        for item in self._query_children():
            yield item

    def clear_property(self, name):
        """
        Clears the specified property from the QueryItem, in line with the
        ``litp update`` command using the ``-d`` option.

        A property cannot be deleted if it:

        - Is required and has no default value
        - Is not updatable by a plugin
        - Is not in the ItemType's structure
        - Is not a property
        - Is contained in a read-only reference item

        :param name: The name of the property to be removed
        :type name: str

        :rtype:   None
        """
        self._set_property(self._model_item, name, None, clear_property=True)

    def get_node(self):
        """
        Return the node this item is on.

        :returns: The node this item is on.
        :rtype:   :class:`litp.core.model_manager.QueryItem` or None
        """
        node_model_item = self._manager.get_node(self._model_item)
        if node_model_item is None:
            return None
        return QueryItem(self._manager, node_model_item)

    def get_ms(self):
        """
        Return the management server this item is on.

        :returns: The management server this item is on.
        :rtype:   :class:`litp.core.model_manager.QueryItem` or None
        """
        ms_model_item = self._manager.get_ms(self._model_item)
        if ms_model_item is None:
            return None
        return QueryItem(self._manager, ms_model_item)

    def get_ancestor(self, item_type_id):
        """
        Return the first ancestor of a specified ``item_type_id``.

        :returns: The first ancestor of a specified ``item_type_id``.
        :rtype:   :class:`litp.core.model_manager.QueryItem` or None
        """
        model_item = self._manager.get_ancestor(self._model_item, item_type_id)
        if model_item is None:
            return None
        return QueryItem(self._manager, model_item)

    def get_cluster(self):
        """
        Return the cluster this item is on.

        :returns: The cluster this item is on.
        :rtype:   :class:`litp.core.model_manager.QueryItem` or None
        """
        return self.get_ancestor("cluster-base")

    def is_node(self):
        """
        Returns True if the item represents a node otherwise returns False.

        :rtype: bool
        """
        return self._model_item.is_node()

    def is_ms(self):
        """
        Returns True if the item represents a management server otherwise \
                returns False.

        :rtype: bool
        """
        return self._model_item.is_ms()

    def is_cluster(self):
        """
        Returns True if the item represents a cluster otherwise returns False.

        :rtype: bool
        """
        return self._model_item.is_cluster()

    def _set_state(self, state, recursive=False):
        self._set_model_item_state(self._model_item, state, recursive)

    def _set_model_item_state(self, item, state, recursive):
        if recursive:
            for child in item.children.itervalues():
                self._set_model_item_state(child, state, True)

        if not self._manager.get_item(item.get_vpath()):
            return
        self._model_item._set_state(state)

    def get_state(self):
        """
        Returns the state of the item as a string. This will be one of:

        * **Initial** - New item
        * **Applied** - Item has been applied by a *run_plan*
        * **Updated** - Previously applied item has updated properties
        * **ForRemoval** - Previously applied item marked for removal next
          *run_plan*
        * **Removed** - Item has been removed

        :rtype: str
        """
        return self._model_item.get_state() if self._model_item else "n/a"

    @property
    def item_type(self):
        """
        Returns the item's type.

        :rtype: Python class type
        """
        return self._model_item.item_type

    @property
    def item_type_id(self):
        """
        Returns the item's type identifier, as defined in model extensions.

        :rtype: str
        """
        return self._model_item.item_type.item_type_id

    @property
    def item_id(self):
        """
        Returns the item's id, as it appears in the vpath.

        :rtype: str
        """
        return self._model_item.item_id

    @property
    def vpath(self):
        """
        Returns the item's vpath

        :rtype: str
        """
        return self._vpath

    def is_initial(self):
        """
        Returns True if the item's state is 'Initial' else returns False

        :rtype: bool
        """
        return self.get_state() == ModelItem.Initial

    def is_applied(self):
        """
        Returns True if the item's state is 'Applied' else returns False

        :rtype: bool
        """
        return self.get_state() == ModelItem.Applied

    def is_updated(self):
        """
        Returns True if the item's state is 'Updated' else returns False

        :rtype: bool
        """

        return self.get_state() == ModelItem.Updated

    def is_for_removal(self):
        """
        Returns True if the item's state is 'ForRemoval' else returns False

        :rtype: bool
        """
        return self.get_state() == ModelItem.ForRemoval

    def is_removed(self):
        """
        Returns True if the item's state is 'Removed' else returns False

        :rtype: bool
        """
        return self.get_state() == ModelItem.Removed

    def get_vpath(self):
        """
        Returns the item's vpath in the Deployment Model

        :rtype: str
        """
        return self.vpath

    def has_initial_dependencies(self):
        """
        Returns whether the item has any descendant items in the Initial state.

        :rtype: bool
        """
        for item in self._manager.query_descends(self._model_item):
            if item.is_initial():
                return True
        return False

    def has_updated_dependencies(self):
        """
        Returns whether the item has any descendant items in the Updated state.

        :rtype: bool
        """
        for item in self._manager.query_descends(self._model_item):
            if item.is_updated():
                return True
        return False

    def has_removed_dependencies(self):
        """
        Returns whether the item has any descendant items in the Removed state.

        :rtype: bool
        """
        for item in self._manager.query_descends(self._model_item):
            if item.is_for_removal():
                return True
        return False

    @property
    def _children(self):
        if self._children_cache is None:
            self._children_cache = OrderedDict()
            for item_id, mitem in self._model_item.children.iteritems():
                qitem = QueryItem(self._manager, mitem)
                qitem._updatable = self._updatable
                self._children_cache[item_id] = qitem
        return self._children_cache

    @property
    def applied_properties(self):
        """
        Returns a dictionary of properties that have been applied.

        :rtype: dict
        """
        return self._model_item.get_applied_properties()

    @property
    def properties(self):
        """
        Returns a dictionary of item properties.

        :rtype: dict
        """
        if self._model_item:
            return self._model_item.get_merged_properties()
        return {}

    def __getattr__(self, name):
        if name in self._model_item._item_type.structure:
            struct_member = self._model_item._item_type.structure[name]
            if isinstance(struct_member, Property):
                value = self.properties.get(name)
            elif isinstance(struct_member, View):
                value = struct_member.callable_method
                if callable(value):
                    try:
                        # TODO: Refactor out this circular import fix
                        from litp.core.plugin_context_api import \
                            PluginApiContext
                        value = value(PluginApiContext(self._manager), self)
                    except ViewError:
                        raise
                    except Exception as ex:
                        raise ViewError(ex)
            else:
                value = self._get_child(name)
            return value

        if isinstance(self._model_item, (CollectionItem, RefCollectionItem)):
            child = self._get_child(name)
            if child is not None:
                return child

        raise AttributeError(
            'No such field "%s" in %s' % (name, self._model_item))

    def __dir__(self):
        attr_list = vars(QueryItem).keys()
        attr_list.extend(self.properties)

        struct = self._model_item._item_type.structure
        attr_list.extend([name for name, obj in struct.iteritems()
                          if not isinstance(obj, (Property, View))])
        return sorted(attr_list)

    def _set_property(self, item, name, value, clear_property=False):
        self._validate_plugin_update(item, name, value, clear_property)
        if self._manager._item_for_removal_exists(item.vpath):
            errors = self._manager._recover_item_for_removal(
                    item.vpath, {name: value}, validate_readonly=True)
            if not isinstance(errors, ModelItem):
                raise self._formatted_validation_error(name, item, errors)
        else:
            inherited_items = [
                    (ref, ref.get_merged_properties(skip_views=True)) for
                ref in self._manager._iterate_inherited_items_recursive(item)]
            item.update_properties({name: value})
            self._manager._update_inherited_items_state(
                    inherited_items, {name: value})

    def _validate_plugin_update(self, item, name, value, clear_property):
        if name not in item._item_type.structure:
            raise AttributeError('No such field "%s" in %s' % (name, item))
        prop = item._item_type.structure[name]
        if not isinstance(prop, Property):
            raise AttributeError(
                'Field "%s" in %s is not a Property' % (name, item))
        if not prop.updatable_plugin:
            raise AttributeError(
                'Field "%s" in %s is not updatable by plugins' % (name, item))
        if self._manager._get_reference_read_only(item.parent, item.item_id):
            raise AttributeError("Read-only reference cannot be updated")
        val_errors = []
        val_errors.extend(self._validate_updatable_plugin_property(
                    item, name, value, clear_property))
        err = self._manager.check_item_is_not_for_removal(
                    item.parent, item.vpath)
        if err:
            val_errors.append(err)
        if val_errors:
            raise self._formatted_validation_error(name, item, val_errors)

    def _formatted_validation_error(self, name, item, errors):
        return AttributeError(
            'ValidationErrors occurred during update of property '
            '"{prop}" on {vpath}:\n{errors}'.format(
                prop=name, vpath=item.vpath,
                errors='\n'.join([repr(error) for error in errors])
            ))

    def _validate_updatable_plugin_property(self, item, name, value,
            clear_property):
        if not clear_property:
            errors = self._manager.validator._run_property_type_validators(
                    item._item_type.structure[name].prop_type, name, value)
        else:
            errors = self._manager.validator._clear_property_validator(
                    item, name)
        updated_item_props = dict(item.properties)
        updated_item_props[name] = value
        errors.extend(
                self._manager.validator._run_item_type_validators(
                    item.item_type, updated_item_props))
        del updated_item_props
        return errors

    def __setattr__(self, name, value):
        if name.startswith("_"):
            object.__setattr__(self, name, value)
            return

        if not self._manager.get_item(self.vpath):
            return

        if not self._updatable:
            raise AttributeError("Not updatable: %s", self)
        item = self._model_item
        if name in item._item_type.structure:
            self._set_property(item, name, value)
        else:
            raise AttributeError(
                "Field %s in %s doesn't exist" % (name, item))

    def _get_child(self, name):
        return self._children.get(name)

    def query(self, item_type_id, **properties):
        """
        Return a list of ``QueryItem`` children objects that match the \
                specified criteria.

        :param item_type_id: Item type id of item to search for.
        :type  item_type_id: str
        :param   properties: Properties of the item to use as search criteria.
        :type    properties: dict

        :returns: list of :class:`litp.core.model_manager.QueryItem` objects \
                found based on the specified criteria.
        :rtype:   list
        """
        model_items = self._manager.query_model_item(
                self._model_item, item_type_id, **properties)
        query_items = []
        for model_item in model_items:
            query_item = QueryItem(
                    self._manager, model_item, updatable=self._updatable)
            query_items.append(query_item)
        return query_items

    def _query_children(self):
        return self._children.itervalues()

    def query_by_vpath(self, vpath):
        """
        Return a :class:`litp.core.model_manager.QueryItem` child object \
            that matches the specified vpath.

        :param vpath: vpath of item to search for.
        :type  item_type_id: str

        :returns: :class:`litp.core.model_manager.QueryItem` object or None
        :rtype:  :class:`litp.core.model_manager.QueryItem` or None
        """
        model_item = self._manager.query_by_vpath(vpath)
        if model_item is not None:
            return QueryItem(self._manager, model_item)
        return None

    def get_source(self):
        """
        Return the source item that this item was inherited from or None \
                if this item was not inherited.

        :returns: The source item that this item was inherited from.
        :rtype:   :class:`litp.core.model_manager.QueryItem` or None
        """
        source_mi = self._model_item.source
        if not source_mi:
            return None
        source_qi = QueryItem(self._manager, source_mi)
        source_qi._updatable = self._updatable
        return source_qi

    def get_parent(self):
        """
        Return the parent item of this item.

        :returns: The parent item of this item.
        :rtype:   :class:`litp.core.model_manager.QueryItem` or None
        """
        parent_mi = self._model_item.parent
        if not parent_mi:
            return None
        parent_qi = QueryItem(self._manager, parent_mi)
        parent_qi._updatable = self._updatable
        return parent_qi


class ModelManagerNextGen(BaseManager):
    def __init__(self):
        super(ModelManagerNextGen, self).__init__()
        self.item_types = dict()
        self.property_types = dict()
        self.validator = ModelValidator(self)
        self.model_dependency_helper = ModelDependencyHelper(self)

    def copy(self):
        mm = ModelManagerNextGen()
        mm.item_types.update(self.item_types)
        mm.property_types.update(self.property_types)
        return mm

    @contextmanager
    def cached_model(self):
        self.data_manager.configure_model_cache()
        yield
        self.data_manager.configure_model()

    def register_property_type(self, property_type):
        """
        :param  property_type: Type of the property to be registered.
        :type   property_type: PropertyType

        """
        if property_type.property_type_id in self.property_types.keys():
            raise Exception("Property type '%s' is already registered" %
                            (property_type.property_type_id))
        self.property_types[property_type.property_type_id] = property_type

    def register_property_types(self, property_types):
        """
        :param  property_types: List of ``PropertyType`` objects to be
            registered.
        :type   property_types: list

        """
        for property_type in property_types:
            self.register_property_type(property_type)

    def register_item_type(self, item_type):
        """
        :param  item_type: ``ItemType`` to be registered.
        :type   item_type: ItemType

        """
        self._check_itemtype_not_registered(item_type)
        self._check_propertytypes_exist(item_type)
        self._check_supertypes_exist(item_type)
        self._check_supertypes_dont_override_properties(item_type)

        self._update_structure_property(item_type)
        self._add_inherited_structure(item_type)

        self.item_types[item_type.item_type_id] = item_type
        self.model_dependency_helper.reset()

    def register_item_types(self, item_types):
        """
        :param  item_types: List of ``ItemType`` instances to be registered.
        :type   item_types: list

        """
        for item_type in item_types:
            self.register_item_type(item_type)

    def _check_itemtype_not_registered(self, item_type):
        if item_type.item_type_id in self.item_types:
            raise Exception("Item type '%s' is already registered" %
                            (item_type.item_type_id))

    def _check_propertytypes_exist(self, item_type):
        for property_type in item_type.get_property_types():
            if property_type.prop_type_id not in self.property_types:
                raise Exception(('Error registering itemtype "%s"'
                            '- property type "%s" not yet registered') %
                            (item_type.item_type_id,
                            property_type.prop_type_id))

    def _update_structure_property(self, item_type):
        for instance in item_type.get_property_types():
            instance.prop_type = self.property_types[instance.prop_type_id]

    def _check_supertypes_exist(self, item_type):
        try:
            supertypes = self._all_supertypes(item_type)
        except KeyError as ex:
            raise ModelManagerException(('Error registering itemtype "%s"'
                             '- base type "%s" not yet registered') %
                             (item_type.item_type_id, ex))

    def _check_supertypes_dont_override_properties(self, item_type):
        for supertype in self._all_supertypes(item_type):
            clashing_properties = set(
                supertype.get_properties()).intersection(
                item_type.get_properties())
            if clashing_properties:
                raise Exception(
                    'Error registering itemtype "%s" - some fields '
                    'are already defined in an extended item: %s' %
                    (item_type.item_type_id, ", ".join(clashing_properties)))

    def _add_inherited_structure(self, item_type):
        for supertype in self._all_supertypes(item_type):
            item_type.structure.update(supertype.structure)

    def create_root_item(self, item_type, _item_path="/", **properties):
        """
        Register root item "/", in order to keep tree structure of all
        ``ModelItem`` instances.
        This makes it easier to use recursive methods that access the entire
        model.

        :param  item_type: Type of the root item.
        :type   item_type: ItemType
        :param properties: Structure of the item as kwargs.
        :type  properties: dict

        """
        items = self._create_model_item(
            None, item_type, "", properties)
        return items[0]

    def create_core_root_items(self):
        """ Create default root items in the model. If you need to create
        another root items, do this here.

        """
        self.create_root_item("root")

    def check_item_type_registered(self, item_type, item_path):
        """
        :param  item_type: Item type name to be checked.
        :type   item_type: str
        :param  item_path: URL of a ``ItemType`` to be checked.
        :type   item_path: str

        """
        if item_type not in self.item_types:
            return ValidationError(
                item_path=item_path,
                error_message="Item type not registered: %s"
                % item_type,
                error_type=constants.INVALID_TYPE_ERROR)

    def check_item_exists(self, item, item_path):
        """
        Return ValidationError if an item doesn't exists within the model.

        :param      item: Instance of an item.
        :type       item: ModelItem
        :param item_path: URL of a item to be checked.
        :type  item_path: str

        """
        if not item:
            return ValidationError(
                item_path=item_path,
                error_message="Path not found",
                error_type=constants.INVALID_LOCATION_ERROR)

    def check_child_exists(self, item_path):
        """
        Return ValidationError if an item already exists within the model.

        :param  item_path: URL of a ``ItemType`` to be checked.
        :type   item_path: str
        """
        item_id = item_path.split("/")[-1]
        if self.has_item(item_path):
            return ValidationError(
                item_path=item_path,
                error_message="Item already exists in model: %s"
                % item_id,
                error_type=constants.ITEM_EXISTS_ERROR)

    def check_item_id(self, item_id):
        """
        Checks that item id adheres to regular expression for identifiers.

        Identifier must be alphanumeric, starting with an alpha character and
        can contain underscore ``_`` and dash ``-``. No other special
        characters are allowed.

        :param item_id: ID of the item
        :type  item_id: str
        """
        item_id_re = r"[a-zA-Z\d_-]+$"
        m = re.match(item_id_re, item_id)
        if m is None:
            return ValidationError(
                property_name=item_id if item_id else "item id",
                error_message="Invalid value for item id: '%s'" % item_id
            )

    def check_has_failed_removal(self, item):
        # LITPCDS-12017: An item which has failed to be removed during a plan
        # will have state ForRemoval and previous state Removed
        if item.is_for_removal() and item.was_removed():
            return ValidationError(
                    item_path=item.vpath,
                    error_message="Cannot update item which has previously "
                                    "failed removal",
                    error_type=constants.METHOD_NOT_ALLOWED_ERROR
                    )

    def check_is_for_removal(self, item, item_path):
        if not item.is_for_removal():
            return ValidationError(
                    item_path=item_path,
                    error_message="Item's state is not ForRemoval:",
                    error_type=constants.INVALID_REQUEST_ERROR
                    )

    def check_item_is_not_for_removal(self, item, item_path):
        if item and item.is_for_removal():
            return ValidationError(
                    item_path=item_path,
                    error_message="Item's parent is marked for removal",
                    error_type=constants.METHOD_NOT_ALLOWED_ERROR
                    )

    def check_source_item_is_not_for_removal(self, item, item_path):
        if item and item.source and item.source.is_for_removal():
            return ValidationError(
                    item_path=item_path,
                    error_message="Item's source item is marked for removal",
                    error_type=constants.METHOD_NOT_ALLOWED_ERROR
                    )

    def check_child_source_item_not_for_removal(self, item, item_path):
        for child in self.query_descends(item):
            if child and child.source and child.source.is_for_removal():
                return ValidationError(
                        item_path=item_path,
                        error_message="Item has a descendant whose"
                        " source item is marked for removal",
                        error_type=constants.METHOD_NOT_ALLOWED_ERROR
                        )

    def _item_for_removal_exists(self, item_path):
        item = self.get_item(item_path)
        if item and item.is_for_removal():
            return True
        return False

    def _validate_recover_item(self, item, item_path, parent, parent_path):
        errors = []

        err = self.check_item_exists(item, item_path)

        if err is None:
            err = self.check_item_exists(parent, parent_path)

        if err is None:
            err = self.check_is_for_removal(item, item_path)

        if err is None:
            err = self.check_has_failed_removal(item)

        if err is None:
            err = self.check_item_is_not_for_removal(parent, item_path)

        if err is None:
            err = self.check_source_item_is_not_for_removal(item, item_path)

        if err is None:
            err = self.check_child_source_item_not_for_removal(item, item_path)

        if err is not None:
            errors.append(err)

        return errors

    def _validate_create(self, item_type, item_path, parent, item_id,
            properties):
        errors = []
        err = None

        if parent and parent.source_vpath:
            err = ValidationError(
                error_message="Can't create items under inherited items",
                item_path=item_path,
                error_type=constants.METHOD_NOT_ALLOWED_ERROR
            )

        if err is None:
            err = self.check_item_type_registered(item_type, item_path)

        if err is None:
            err = self.check_item_id(item_id)

        if err is None:
            err = self.check_item_exists(parent, item_path)

        if err is None:
            err = self.check_item_is_not_for_removal(parent, item_path)

        if err is None:
            err = self.check_child_exists(item_path)

        if err is not None:
            errors.append(err)

        if not errors:
            errors.extend(
                self._check_allowed_child(parent, item_type, item_id))

        if not errors:
            item_type_instance = self.item_types[item_type]
            complete_properties = self._get_complete_properties(
                    item_type_instance, properties)
            errors.extend(
                self.validator.validate_properties(
                    item_type_instance, complete_properties, PROPERTY_WRITE)
            )

        return errors

    def _get_complete_properties(self, item_type, properties):
        """Build complete dict of properties for validation.

        If a property has a default and has not been specified by the user,
        add the default value. This is only relevant to validation at create.
        Also, Views are not included here as they only exists after creation.

        :param item_type: The ItemType instance to build a complete set
            of properties from
        :type item_type: :class:`litp.core.model_type.ItemType`
        :param properties: The specified properties at create item time
        :type properties: dict

        :rtype:    dict
        :returns:  Dictionary of specified properties and unspecified default
            properties
        """
        complete_properties = dict()
        for name, instance in item_type.structure.iteritems():
            if isinstance(instance, Property) and instance.default is not None:
                complete_properties[name] = instance.default
        complete_properties.update(properties)
        return complete_properties

    def _check_allowed_child_model_item(self, parent, item_type_id, item_id,
                                        is_reference, source_item):
        errors = []
        item_type_obj = parent._item_type.structure.get(item_id, None)
        if not item_type_obj:
            errors.append(
                ValidationError(
                    error_message=(
                        "'%s' (type: '%s') is not an allowed child of %s" %
                        (item_id, item_type_id, parent.vpath)
                    ),
                    error_type=constants.CHILD_NOT_ALLOWED_ERROR,
                    property_name=item_type_id
                )
            )
        elif not self._is_type(item_type_id, item_type_obj.item_type_id):
            errors.append(
                ValidationError(
                    error_message=(
                        "'%s' is not an allowed type for child '%s'" %
                        (item_type_id, item_id)
                    ),
                    error_type=constants.INVALID_CHILD_TYPE_ERROR,
                    item_path=parent.parent_vpath
                )
            )
        elif isinstance(item_type_obj, Reference) and not is_reference:
            errors.append(
                ValidationError(
                    error_message=(
                        "'%s' must be an inherited item" %
                        (item_id)
                    ),
                    error_type=constants.CHILD_NOT_ALLOWED_ERROR,
                    item_path=parent.vpath
                )
            )
        elif source_item and source_item.is_collection() and \
                is_reference and not isinstance(item_type_obj, RefCollection):
            errors.append(
                ValidationError(
                    error_message=(
                        "'%s' must not be a reference to a collection of '%s'"
                        % (item_id, item_type_id)
                    ),
                    error_type=constants.CHILD_NOT_ALLOWED_ERROR,
                    item_path=parent.vpath
                )
            )
        return errors

    def _check_allowed_child_collection_item(self, parent, item_type, item_id,
                                             is_reference, source_item):
        errors = []
        if not self._is_type(item_type, parent._item_type.item_type_id):
            errors.append(
                ValidationError(
                    item_path=parent.vpath,
                    error_message=(
                        "'%s' is not an allowed type for collection of"
                        " item type '%s'" %
                        (item_type, parent._item_type.item_type_id)
                    ),
                    error_type=constants.INVALID_CHILD_TYPE_ERROR
                )
            )
        elif is_reference:
            if not (parent and parent.source_vpath and source_item and
                    parent.source_vpath == source_item.parent_vpath):
                errors.append(
                    ValidationError(
                        error_message=(
                            "'%s' must not be an inherited item" %
                            (item_id)
                        ),
                        error_type=constants.CHILD_NOT_ALLOWED_ERROR,
                        item_path=parent.vpath
                    )
                )
        return errors

    def _check_allowed_child_refcollection_item(self, parent,
                                                item_type, item_id,
                                                is_reference, source_item):
        errors = []
        if not self._is_type(item_type, parent._item_type.item_type_id):
            errors.append(
                ValidationError(
                    item_path=parent.parent.vpath,
                    error_message=(
                        "'%s' is not an allowed type for reference collection "
                        "of item type '%s'" %
                        (item_type, parent._item_type.item_type_id)
                    ),
                    error_type=constants.INVALID_CHILD_TYPE_ERROR
                )
            )
        elif not is_reference:
            errors.append(
                ValidationError(
                    error_message=(
                        "'%s' must be an inherited item" %
                        (item_id)
                    ),
                    error_type=constants.CHILD_NOT_ALLOWED_ERROR,
                    item_path=parent.vpath
                )
            )
        return errors

    def _check_allowed_child(self, parent, item_type, item_id,
                             is_reference=False, source_item=None):
        if isinstance(parent, RefCollectionItem):
            return self._check_allowed_child_refcollection_item(
                parent, item_type, item_id, is_reference, source_item)
        elif isinstance(parent, CollectionItem):
            return self._check_allowed_child_collection_item(
                parent, item_type, item_id, is_reference, source_item)
        else:
            return self._check_allowed_child_model_item(
                parent, item_type, item_id, is_reference, source_item)

    def _create_single_model_item(self, parent,
                                  item_type, item_id, properties):
        parent_vpath = parent.vpath if parent else None
        item = ModelItem(self, item_type, item_id, parent_vpath, properties)
        self.data_manager.model.add(item)
        log.trace.debug("created item: %s", item)
        return item

    def _create_collection_item(self, parent,
                                item_type, item_id, properties):
        parent_vpath = parent.vpath if parent else None
        item = CollectionItem(self, item_type, item_id, parent_vpath,
                              properties)
        self.data_manager.model.add(item)
        log.trace.debug("created item: %s", item)
        return item

    def _create_refcollection_item(self, parent,
                                   item_type, item_id, properties):
        parent_vpath = parent.vpath if parent else None
        item = RefCollectionItem(self, item_type, item_id, parent_vpath,
                                 properties)
        self.data_manager.model.add(item)
        log.trace.debug("created item: %s", item)
        return item

    def _create_model_item_defaults(self, item):
        items = []
        for subitem_id, subitem_type in item.item_type.structure.iteritems():
            if isinstance(subitem_type, Property):
                if subitem_type.default and subitem_id not in item.properties:
                    item.set_property(subitem_id, subitem_type.default)
            elif isinstance(subitem_type, Child):
                if subitem_type.required:
                    items.extend(
                        self._create_model_item(
                            item, subitem_type.item_type_id, subitem_id, {}))
            elif isinstance(subitem_type, Collection):
                item_type = self.item_types[subitem_type.item_type_id]
                if type(subitem_type) is Collection:
                    items.append(
                        self._create_collection_item(
                            item, item_type, subitem_id, {}))
                elif type(subitem_type) is RefCollection:
                    items.append(
                        self._create_refcollection_item(
                            item, item_type, subitem_id, {}))
                else:
                    raise TypeError("invalid subitem_type: %s" % subitem_type)
        return items

    def _create_model_item(self, parent, item_type_id, item_id, properties,
                           source_item=None):
        if item_type_id not in self.item_types:
            raise ValueError(
                "item type %s is not registered" % item_type_id)
        item_type = self.item_types[item_type_id]
        items = []
        item = self._create_single_model_item(
            parent, item_type, item_id, properties)
        items.append(item)
        if source_item:
            item.source_vpath = source_item.vpath
        else:
            items.extend(self._create_model_item_defaults(item))
        return items

    def _create_children_from_source_items(self, items):
        children = []
        for item in items:
            children.extend(
                self._create_children_from_source_item(item))
        return children

    def _create_children_from_source_item(self, item):
        items = []
        source_item = self.get_item(item.source_vpath)
        source_item_children = self.get_children(source_item)
        for child_id, child in source_item_children.iteritems():
            if child.is_for_removal():
                continue

            child_type = self.item_types[child.item_type_id]
            if isinstance(child, CollectionItem):
                subitem = self._create_collection_item(
                    item, child_type, child_id, {})
            elif isinstance(child, RefCollectionItem):
                subitem = self._create_refcollection_item(
                    item, child_type, child_id, {})
            elif isinstance(child, ModelItem):
                subitem = self._create_single_model_item(
                    item, child_type, child_id, {})
            else:
                raise TypeError("invalid child: %s", child)

            subitem.source_vpath = child.vpath
            items.append(subitem)
            items.extend(
                self._create_children_from_source_item(subitem))

        return items

    def _create_item(self, item_type, item_path, properties):
        parent_vpath, item_id = self.split_path(item_path)
        parent = self.get_item(parent_vpath) if parent_vpath else None
        errors = self._validate_create(item_type, item_path, parent, item_id,
            properties)

        if not errors:
            items = self._create_model_item(
                parent, item_type, item_id, properties)
            self.check_model_item_deprecation(items[0])

            item = items[0]
            # FIXME: Overly intricate solution to LITPCDS-6217.
            for pname in properties:
                if pname in ["is_locked"] and item.is_node():
                    prop = item.item_type.structure[pname]
                    item.set_property("is_locked", prop.default)

            log.audit.info("Created item %s" % item_path)
            for inherited_item in \
                    self._iterate_inherited_items_recursive(parent):
                self._create_inherited_tree(
                    item_path, inherited_item, item_id, {})
            return items[0]
        return errors

    def _recover_item_for_removal(self, item_path, properties,
                                  validate_readonly=True):
        parent_vpath, item_id = self.split_path(item_path)
        parent = self.get_item(parent_vpath) if parent_vpath else None
        parent_path = item_id  # TODO: ??
        item = self.get_item(item_path)

        errors = self._validate_recover_item(item, item_path, parent,
                parent_path)
        if not errors:
            self._recover_item_for_removal_down(item)
            errors = self._update_item(item.vpath, properties,
                                       validate_readonly=validate_readonly)
        if errors:
            return errors
        return item

    def _recover_item_for_removal_down(self, item):
        item.set_previous_state()

        for child in self.get_children(item).itervalues():
            self._recover_item_for_removal_down(child)

        for inherited_item in self._iterate_inherited_items_recursive(item):
            if not inherited_item.has_overwritten_properties:
                inherited_item.set_previous_state()

    def create_item(self, item_type, vpath, **properties):
        """ Parallel method to create_item so as not to break backward
        compatibility. This will return a dict containing the validation
        responses. If no validation errors then the item is created.

        """
        if self._item_for_removal_exists(vpath):
            return self._recover_item_for_removal(vpath, properties)
        else:
            return self._create_item(item_type, vpath, properties)

    def _create_inherited_tree(self, source_item_path, parent, item_id,
                               properties):
        source_item = self.get_item(source_item_path)
        items = self._create_model_item(
            parent, source_item.item_type_id, item_id,
            properties, source_item=source_item)
        items.extend(
            self._create_children_from_source_items(items))
        return items

    def _create_inherited(self, source_item_path, item_path, properties):
        parent_vpath, item_id = self.split_path(item_path)
        parent = self.get_item(parent_vpath) if parent_vpath else None
        errors = []
        source_item_path = source_item_path.rstrip("/")

        errors.extend(self._validate_inherited(source_item_path, item_path,
            parent, item_id, properties))

        if not errors:
            items = self._create_inherited_tree(
                source_item_path, parent, item_id, properties)
            log.audit.info("Created inherited item %s" % item_path)
            for inherited_item in \
                    self._iterate_inherited_items_recursive(parent):
                self._create_inherited_tree(
                    item_path, inherited_item, item_id, {})
            return items[0]
        return errors

    def create_inherited(self, source_item_path, item_path, **properties):
        if self._item_for_removal_exists(item_path):
            item = self.get_item(item_path)
            if not item.source_vpath:
                return [ValidationError(
                    error_message="Item already exists in model: %s" %
                                  item.item_id,
                    item_path=item_path,
                    error_type=constants.ITEM_EXISTS_ERROR
                )]
            elif item.source_vpath != source_item_path:
                return [ValidationError(
                    error_message="Cannot re-inherit item "
                                    "from different source",
                    item_path=item_path,
                    error_type=constants.METHOD_NOT_ALLOWED_ERROR
                )]
            return self._recover_item_for_removal(item_path, properties)
        else:
            return self._create_inherited(source_item_path, item_path,
                                          properties)

    def _validate_inherited(self, source_item_path, item_path, parent, item_id,
            properties):
        errors = []
        err = None

        if properties and self._get_reference_read_only(parent, item_id):
            err = ValidationError(
                error_message="Read-only reference cannot be created with "
                    "properties",
                item_path=item_path,
            )

        source_item = self.get_item(source_item_path)

        if err is None:
            if not source_item:
                err = ValidationError(
                    error_message="Source item %s doesn't exist" %
                                    source_item_path,
                    item_path=source_item_path,
                    error_type=constants.INVALID_LOCATION_ERROR)

        if err is None:
            if source_item.is_for_removal():
                err = ValidationError(
                    error_message="Can't inherit item that is "
                                  "marked for removal",
                    item_path=item_path,
                    error_type=constants.METHOD_NOT_ALLOWED_ERROR
                )

        if err is None:
            if parent and parent.source_vpath:
                if parent.source_vpath != source_item.parent_vpath:
                    err = ValidationError(
                        error_message="Cannot re-inherit item "
                                        "from different source",
                        item_path=item_path,
                        error_type=constants.METHOD_NOT_ALLOWED_ERROR
                    )

        if err is None:
            err = self.check_item_id(item_id)

        if err is None:
            err = self.check_item_exists(parent, item_path)

        if err is None:
            err = self.check_item_is_not_for_removal(parent, item_path)

        if err is None:
            err = self.check_child_exists(item_path)

        if err is not None:
            errors.append(err)

        if not errors:
            errors.extend(
                self._check_allowed_child(
                    parent,
                    source_item.item_type_id, item_id, is_reference=True,
                    source_item=source_item
                )
            )

        if not errors:
            new_properties = {}
            for property_name, property_value in \
                    source_item.get_merged_properties(
                            skip_views=True).iteritems():
                new_properties[property_name] = property_value
            for property_name, property_value in properties.iteritems():
                if not property_value:
                    continue
                new_properties[property_name] = property_value

            item_type_instance = source_item.item_type
            errors.extend(
                self.validator.validate_properties(
                    item_type_instance, new_properties, PROPERTY_WRITE)
            )

        return errors

    def _get_updatable_plugin_properties(self, item_type, properties):
        updatable_plugin_properties = {}
        for name, value in properties.iteritems():
            if name in item_type.structure:
                prop = item_type.structure[name]
                if hasattr(prop, "updatable_plugin"):
                    if prop.updatable_plugin:
                        updatable_plugin_properties[name] = value
        return updatable_plugin_properties

    def _validate_update_inherited_items(
            self, inherited_item, properties_for_update, validate_readonly):
        property_updates = {}
        for property_name, property_value in properties_for_update.iteritems():
            if property_name not in inherited_item.get_properties() or \
            property_value is None:
                property_updates[property_name] = property_value
        errors = self._validate_update(
            inherited_item, inherited_item.vpath,
            property_updates, validate_readonly=validate_readonly,
            is_source_update=True)
        return errors

    def _update_item(self, vpath, properties, validate_readonly=True):
        item = self.get_item(vpath)

        errors = self._validate_update(item, vpath, properties,
                validate_readonly=validate_readonly)
        if not errors:
            properties_for_update = properties
            if not item.source_vpath:
                for property_name, property_value in \
                        properties_for_update.iteritems():
                    if property_value is None:
                        item_type = item.item_type
                        field = item_type.structure.get(property_name)
                        if field and field.default:
                            property_value = field.default
                    properties[property_name] = property_value

            inherited_items = []
            for inherited_item in \
                    self._iterate_inherited_items_recursive(item):
                inherited_items.append((
                    inherited_item,
                    inherited_item.get_merged_properties(skip_views=True),
                ))
                errors = self._validate_update_inherited_items(
                    inherited_item, properties_for_update, validate_readonly)
                if errors:
                    return errors

            item.update_properties(properties)
            updated_msg = ', '.join(["'" + str(k) + "'" + ": " + str(v) for
                k, v in properties.iteritems()])
            self.check_model_item_deprecation(item)
            log.audit.info("Updated item %s. Updated properties: %s" %
                (vpath, updated_msg))

            # any non-configuration properties are applied immediately
            self._apply_inherited_items_non_configs(inherited_items,
                                                    properties)
            self._update_inherited_items_state(inherited_items, properties)

            return item
        return errors

    def _apply_inherited_items_non_configs(self, inherited_items, properties):
        for item, _ in inherited_items:
            item.apply_non_config_properties(properties, overwrite=False)

    def _update_inherited_items_state(self, inherited_items, properties):
        for inherited_item, old_properties in inherited_items:
            if inherited_item.all_properties_overwritten(properties):
                continue
            new_properties = inherited_item.get_merged_properties(
                    skip_views=True)

            self._update_inherited_item_state(inherited_item, new_properties)

    def _update_inherited_item_state(self, item, new_properties):
        inherited_applied_properties = item.get_applied_properties(True)
        if inherited_applied_properties == new_properties:
            if (item.is_updated() or item.is_for_removal()) and \
                    item.applied_properties_determinable:
                item.set_applied()
            elif (item.is_applied() or item.is_for_removal()) and not \
                    item.applied_properties_determinable:
                item.set_updated()
        else:
            if item.is_for_removal() and item.was_initial() and not \
                    item.applied_properties_determinable:
                item.set_initial()
            elif item.is_applied() or item.is_for_removal():
                item.set_updated()
        if item.parent.is_for_removal():
            item.set_for_removal()
        item.set_state_child_collection()

    def _update_or_replace_item(self, vpath, properties, validate_readonly):
        item = self.get_item(vpath)
        errors = self._validate_update(item, vpath, properties,
                validate_readonly=validate_readonly)
        if errors:
            return errors
        if item.is_for_removal():
            errors = self._recover_item_for_removal(
                vpath, properties, validate_readonly=validate_readonly)
        else:
            errors = self._update_item(
                vpath, properties, validate_readonly=validate_readonly)
        return errors

    def update_item(self, vpath, **properties):
        return self._update_or_replace_item(vpath, properties, True)

    def merge_item(self, vpath, **properties):
        item = self.get_item(vpath)
        new_properties = dict(properties)
        if item:
            for pname in new_properties.keys():
                if pname not in item._item_type.structure:
                    del new_properties[pname]
                if pname in ["is_locked"] and item.is_node():
                    new_properties[pname] = item.is_locked
            existing_properties = item.get_properties(skip_views=True)
            log.audit.info(
                "Merging %s with %s", existing_properties, new_properties)
        return self._update_or_replace_item(vpath, new_properties, True)

    def replace_item(self, vpath, **properties):
        existing_item = self.get_item(vpath)
        new_properties = dict(properties)
        if existing_item:
            existing_properties = existing_item.get_properties(skip_views=True)
            for pname, pvalue in existing_properties.iteritems():
                prop = existing_item._item_type.structure[pname]
                if pname not in new_properties:
                    if (prop.updatable_plugin and not prop.updatable_rest and
                       (not existing_item.is_initial()
                        or not existing_item.applied_properties_determinable)):
                        # ignore plugin_updatable=T and prop.updatable_rest=F
                        # when item is not Inital
                        pass
                    elif prop.default:
                        # reset to the default value if default exists
                        new_properties[pname] = prop.default
                    else:
                        new_properties[pname] = None

                # FIXME: Overly intricate solution to LITPCDS-6217.
                if pname in ["is_locked"] and existing_item.is_node():
                    new_properties[pname] = existing_item.is_locked

            log.audit.info(
                "Replacing %s with %s", existing_properties, new_properties)
        return self._update_or_replace_item(vpath, new_properties, True)

    def _get_reference_read_only(self, parent, item_id):
        while parent:
            parent_item_types = self.item_types[parent.item_type_id].structure
            if not isinstance(parent, (CollectionItem, RefCollectionItem)):
                if item_id in parent_item_types:
                    item_type = parent_item_types[item_id]
                    if isinstance(item_type, (RefCollection, Reference)):
                        if item_type.read_only:
                            return item_type.read_only

            item_id = parent.item_id
            parent = parent.parent
        return None

    def _validate_update(self, item, vpath, properties,
                         validate_readonly=True, is_source_update=False):
        errors = []
        err = self.check_item_exists(item, vpath)

        if err is not None:
            errors.append(err)

        if not errors:
            if properties and self._get_reference_read_only(
                    item.parent, item.item_id):
                errors.extend([ValidationError(
                    error_message="Read-only reference cannot be updated",
                    item_path=vpath,
                )])

        if not errors:
            if item.is_collection():
                err = ValidationError(
                    error_message="Properties cannot be set on collections",
                    item_path=vpath,
                    error_type=constants.PROP_NOT_ALLOWED_ERROR
                )
                errors.append(err)
            else:
                if validate_readonly and (not item.is_initial()\
                    or item.is_node()):
                    errors.extend(self._validate_readonly_properties(
                        item, properties))

                if item.source_vpath:
                    new_properties = {}
                    for property_name, property_value in \
                            item.get_merged_properties(
                                    skip_views=True).iteritems():
                        new_properties[property_name] = property_value
                    for property_name, property_value in \
                            properties.iteritems():
                        if property_value is None:
                            if property_name not in item.get_properties() \
                               and is_source_update:
                                del new_properties[property_name]
                                continue
                            else:
                                continue
                        new_properties[property_name] = property_value
                else:
                    new_properties = {}
                    err, new_properties = self._get_combined_properties(
                        item, properties)
                    errors.extend(err)
                errors.extend(
                    self.validator.validate_properties(
                        item.item_type, new_properties, PROPERTY_WRITE,
                        is_reference=False)
                )

        return errors

    def _get_readonly_properties(self, item, properties):
        readonly_properties = {}
        for name, value in properties.iteritems():
            if name in item._item_type.structure:
                prop = item._item_type.structure[name]
                if isinstance(prop, Property) and not prop.updatable_rest:
                    readonly_properties[name] = value
        return readonly_properties

    def _validate_readonly_properties(self, item, properties):
        def _update_required(item, prop):
            new_val = readonly_properties[prop]
            if item.is_updated():
                if not prop in item.get_applied_properties():
                    return False
                current_val = item.get_applied_properties()[prop]
            else:
                if not prop in item.get_merged_properties():
                    return False
                current_val = item.get_merged_properties()[prop]
            return new_val != current_val

        errors = []
        readonly_properties = self._get_readonly_properties(item, properties)
        for prop in readonly_properties:
            if not _update_required(item, prop):
                continue
            if (item.is_node() and prop in ['is_locked']) or \
                    prop in item.get_applied_properties():
                errors.append(ValidationError(
                    error_message="Unable to modify readonly "
                    "property: %s" % prop,
                    item_path=item.vpath,
                    property_name=prop,
                    error_type=constants.INVALID_REQUEST_ERROR))
        return errors

    def _get_combined_properties(self, item, prop_updates):
        errors = []
        combined_props = item._properties.copy()
        for key, value in combined_props.items():
            if callable(value):
                del combined_props[key]
        for key, value in prop_updates.items():
            if value is None and key in combined_props:
                del combined_props[key]
            elif value is not None:
                combined_props[key] = value
            else:
                errors.extend([ValidationError(
                    error_message="Unable to delete property: %s" % key,
                    item_path=item.vpath,
                    property_name=key,
                    error_type=constants.INVALID_REQUEST_ERROR)])
        return (errors, combined_props)

    def validate_model(self):
        """Validate each item within model with its own validate() method. """
        errors = []
        states = set([
            state for state in ModelItem.ALL_STATES
            if state != ModelItem.ForRemoval])
        for item in self.data_manager.model.query_by_states(states):
            errors.extend(
                [err for err in self._validate_model_item(item)]
            )
        return errors

    def _is_type(self, item_type_id, base_type_id):
        item_type = self.item_types[item_type_id]
        return base_type_id == item_type_id or \
            base_type_id in self._all_supertype_ids(item_type)

    def _all_supertype_ids(self, item_type):
        return [item_type.item_type_id for item_type in \
            self._all_supertypes(item_type)]

    def _all_supertypes(self, item_type):
        supertypes = []
        while item_type.extend_item:
            supertypes.append(self.item_types[item_type.extend_item])
            item_type = self.item_types[item_type.extend_item]
        return supertypes

    def split_path(self, vpath):
        if vpath == "/":
            return None, ""
        parent_vpath, item_id = vpath.rsplit("/", 1)
        if parent_vpath == "":
            parent_vpath = "/"
        return parent_vpath, item_id

    def generate_path(self, parent_vpath, item_id):
        if not parent_vpath:
            vpath = "/"
        elif parent_vpath == "/":
            vpath = "/" + item_id
        else:
            vpath = parent_vpath + "/" + item_id
        return vpath

    def find_modelitem(self, item_type_id, properties):
        """
        Find a ``ModelItem`` instance within model manager's items.
        Returned value may NOT be a collection nor a reference.

        :param item_type_id: Item type id of item to be found.
        :type  item_type_id: str
        :param   properties: Structure of the item.
        :type    properties: dict

        :rtype:    ModelItem
        :returns:  Found model item

        """
        matched_items = self.find_modelitems(item_type_id, properties)
        matched_items_filtered = [
            item for item in matched_items if not
                item.is_for_removal() and not item.is_removed()]
        if len(matched_items_filtered) == 1:
            return matched_items_filtered[0]
        if len(matched_items) == 1:
            return matched_items[0]
        return None

    def find_modelitems(self, item_type_id, properties=None):
        """
        Find all ``ModelItem`` instances within model manager's items.
        Returned value may NOT be a collection nor a reference.

        :param item_type_id: Item type id of items to be found.
        :type  item_type_id: str
        :param   properties: Structure of the item.
        :type    properties: dict

        :rtype:    list
        :returns:  List of of found model items

        """
        if properties is None:
            properties = {}

        model_items = [
            item for item in self.data_manager.model.query() if
            type(item) is not CollectionItem
        ]

        matched_items = [
            model_item for model_item in model_items
            if self._match(model_item, item_type_id, properties)
        ]
        return matched_items

    def _has_ancestry_with_apd_false(self, item):
        while item.parent:
            if not item.parent.applied_properties_determinable:
                return True
            item = item.parent
        return False

    def _queue_children(self, parent, queue):
        for child in parent.children.itervalues():
            queue.append(child)

    def _has_siblings_or_their_descendants_apd_false(self, item):
        if not item.parent:
            return False
        queue = deque()
        self._queue_children(item.parent, queue)
        if item in queue:
            queue.remove(item)
        while queue:
            item = queue.popleft()
            if not item.applied_properties_determinable:
                return True
            self._queue_children(item, queue)
        return False

    def _can_item_be_deleted(self, item):
        if not item.applied_properties_determinable:
            return False

        if self._has_ancestry_with_apd_false(item):
            return False

        if self._has_siblings_or_their_descendants_apd_false(item):
            return False

        for iitem in self._iterate_inherited_items_recursive(item):
            if not self._can_item_be_deleted(iitem):
                return False

        # non-recursive, only checks children
        if not (item.is_initial() or item.is_removed()):
            return False
        for child in item.children.itervalues():
            if not (child.is_initial() or child.is_removed()):
                return False
        return True

    def _remove_item_recursive(self, item, cascade=False):
        for inherited_item in [
            iitem for iitem in
            self._iterate_inherited_items_recursive(item)
        ]:
            self._remove_item(inherited_item)

        for child in item.children.values():
            self._remove_item_recursive(child, cascade=True)

        if self._can_item_be_deleted(item):
            for child in item.children.values():
                if child.is_removed():
                    self._delete_removed_item(child)
            self._set_item_removed(item)
        else:
            for child in item.children.values():
                if child.is_removed():
                    if child.is_collection():
                        self._set_item_for_removal(child)
                    else:
                        self._delete_removed_item(child)
            self._set_item_for_removal(item)

    def _remove_item(self, item):
        """
        Initiates the removal of a :class:`~litp.core.model_item.ModelItem`
        from the model. This method will cause ``item`` and all the items in
        its progeny to enter either the ``ForRemoval`` or the ``Removed``
        state.
        In the former case, a plan execution will be required to move
        the item to the ``Removed`` state.
        In the latter case, ``item`` is immediately deleted from the model.

        :param item: The item to be removed from the deployment model
        :type item: :class:`~litp.core.model_item.ModelItem`
        """

        self._remove_item_recursive(item)

        if item.is_removed():
            self._delete_removed_item(item)

    def _set_item_removed(self, item):
        log.trace.debug("set item removed: %s", item.vpath)
        item.set_removed()

    def _set_item_for_removal(self, item):
        log.trace.debug("set item for removal: %s", item.vpath)
        item.set_for_removal()

    def _delete_removed_item(self, item, validate_inherit=True):
        """
        Deletes a :class:`~litp.core.model_item.ModelItem` from the deployment
        model. ``item`` must be in the ``Removed`` state when this method is
        called. A :class:`~litp.core.exceptions.ModelManagerException` is
        raised if deleting ``item`` would result in model inconsistency.

        :param item: The item to be deleted from the deployment model
        :type item: :class:`~litp.core.model_item.ModelItem`

        :param validate_inherit: If ``True``, checks whether deleting ``item``
            would break model consistency by causing inherited items to lose
            their source.
        :type validate_inherit: bool
        """

        # Allow xml replace and merge to remove item, as it is recreated after
        if validate_inherit:
            for inherit_item in self._iterate_inherited_items_recursive(item):
                if inherit_item.is_removed():
                    continue
                log.trace.warning(
                    "Item {0} cannot be deleted from the model because item " \
                    "{1} which inherits from it has not been removed.".format(
                        item.vpath, inherit_item.vpath
                    )
                )
                raise ModelManagerException(
                        "model inconsistency if removing item")

        for child in item.children.itervalues():
            if child.is_removed():
                continue
            log.trace.warning(
                "Item {0} cannot be deleted from the model because its "
                "child item {1} has not been removed.".format(
                    item.vpath, child.vpath
                )
            )
            raise ModelManagerException("model inconsistency if removing item")

        self.data_manager.model.delete(item)
        log.audit.info("Deleted item {0}".format(item))

    def remove_item(self, vpath):
        """ Remove ``ModelItem`` from ``ModelManager``. In fact ``ModelItem``
        that is in ``Initial`` state and its applied properties are
        determinable, will be removed immediately otherwise it will be marked
        as ``ForRemoval``.

        :param vpath: URL to the ``ModelItem``.
        :type  vpath: str

        """
        if vpath != '/':
            vpath = vpath.rstrip('/')
        item = self.get_item(vpath)
        errors = []
        error = self.check_item_exists(item, vpath)
        parent_vpath, item_id = self.split_path(vpath)
        parent = self.get_item(parent_vpath) if parent_vpath else None
        if item is not None:
            item_type_id = item.item_type.item_type_id
            if item_type_id == 'root':
                error = ValidationError(
                    item_path='/',
                    error_message=constants.ERROR_MESSAGE_CODES.get(
                        constants.METHOD_NOT_ALLOWED_ERROR),
                    error_type=constants.METHOD_NOT_ALLOWED_ERROR
                )
            elif item_type_id == 'sshd-config' and not item.is_initial():
                error = ValidationError(
                    item_path=vpath,
                    error_message=constants.ERROR_MESSAGE_CODES.get(
                        constants.METHOD_NOT_ALLOWED_ERROR),
                    error_type=constants.METHOD_NOT_ALLOWED_ERROR
                )
            elif vpath in [
                "/software",
                "/infrastructure",
                "/infrastructure/storage",
                "/infrastructure/networking",
                "/ms",
                "/snapshots"
                "/litp"
                ]:
                # These items are not allowed to enter the ForRemoval state
                error = ValidationError(
                    item_path=vpath,
                    error_message=constants.ERROR_MESSAGE_CODES.get(
                        constants.METHOD_NOT_ALLOWED_ERROR),
                    error_type=constants.METHOD_NOT_ALLOWED_ERROR
                )
            elif item.is_collection():
                error = ValidationError(
                    item_path=vpath,
                    error_message="Cannot directly delete Collection item",
                    error_type=constants.METHOD_NOT_ALLOWED_ERROR
                )
        if error:
            errors.append(error)
            return errors

        self._remove_item(item)
        if not errors:
            return item
        return errors

    def _iterate_inherited_items_recursive(self, source_item):
        for item in self.data_manager.model.query_inherited(source_item):
            yield item
            for child_item in self._iterate_inherited_items_recursive(item):
                yield child_item

    def create_json_response_object(self,
                                    data=None,
                                    messages=None,
                                    status=None):
        return {'data': data,
                'messages': messages or [],
                'status': status
                }

    def show(self, item_path):
        """
        Return data for 'litp show' command.

        :param item_path: URL of a ``ModelItem`` to be shown.
        :type  item_path: str
        """
        item = self.get_item(item_path)
        if item:
            return item.show_item()
        else:
            raise ModelManagerException("No such item: %s" % (item_path,))

    def _match(self, model_item, item_type_id, properties):
        return model_item._extends(item_type_id) and \
                model_item._properties_match(properties)

    def snapshot_path(self, name):
        return "{0}/{1}".format(constants.SNAPSHOT_BASE_PATH, name)

    def set_all_applied(self, exceptions=None):
        """ Set all ``ModelItem``s' state within ``ModelManager`` to
        ``Applied``.

        :param exceptions: list of item vpaths that do not have to be set
        :type exceptions: list
        """
        if not exceptions:
            exceptions = []
        states = set([
            state for state in ModelItem.ALL_STATES
            if state != ModelItem.Applied])
        for item in self.data_manager.model.query_by_states(states):
            if not any(item.is_instance(exc_type) for exc_type in exceptions):
                log.trace.debug("set_all_applied '%s' (%s: %s) to Applied",
                                item.vpath,
                                item.__class__.__name__,
                                item.item_type_id)
                item.set_applied()

    def _set_items_to_initial(self, item, exclude_paths):
        self._set_initial_recursive(item, exclude_paths)
        log.trace.debug("Set items to initial from: %s", item)
        log.trace.debug("exclude path prefixes: %s", exclude_paths)

    def _set_initial_recursive(self, item, exclude_paths, cascade=False):
        for iitem in self._iterate_inherited_items_recursive(item):
            for inherited_item in iitem:
                self._set_initial_recursive(inherited_item, exclude_paths)
                log.audit.debug("Set to initial item %s", inherited_item)

        for child in item.children.values():
            self._set_initial_recursive(child, exclude_paths, cascade=True)

        self._set_item_initial(item, exclude_paths)

    def _set_item_initial(self, item, exclude_paths):
        # TORF-539617 - improve model_manager.py exclude_paths check
        # regex use word boundary for item.vpath to match items in
        # exclude_paths
        if all(not re.search(r'{0}\b'.format(x.rstrip('/')), item.vpath)
             for x in exclude_paths):
            log.trace.debug("set item to initial: %s", item.vpath)
            item.set_initial()
            if item.is_initial():
                item.reset_applied_properties()
                item._set_applied_properties_determinable(True)

    def set_snapshot_applied(self, name):
        """ Set Snapshot ``ModelItem``s' state to ``Applied``.
        """
        snapshot_item = self.get_item(self.snapshot_path(name))
        if snapshot_item:
            snapshot_item.set_applied()
            # set also the parent collection
            snapshot_item.parent.set_applied()

    def set_snapshot_for_removal(self, name):
        """ Set Snapshot ``ModelItem``s' state to ``ForRemoval``.
        """
        snapshot_item = self.get_item(self.snapshot_path(name))
        if snapshot_item:
            snapshot_item.set_for_removal()

    def create_snapshot_item(self, name):
        return self.create_item(
            "snapshot-base", self.snapshot_path(name), timestamp=None
        )

    def _remove_all_snapshots(self):
        snapshots = self.query('snapshot-base')
        for snapshot in snapshots:
            self.remove_snapshot_item(snapshot.item_id)

    def remove_snapshot_item(self, name):
        """
        Sets the snapshot item to removed state and removes it.
        """
        snapshot_item = self.get_item(self.snapshot_path(name))
        if snapshot_item:
            log.trace.debug("Removing snapshot item")
            snapshot_item.set_removed()
            self._delete_removed_item(snapshot_item)

    def delete_removed_items_after_plan(self):
        """
        Deletes items that are in the ``Removed`` state at the end of a plan.
        In the event that deleting an item in the ``Removed`` state would break
        model consistency, that item and its children are reset to the
        ``ForRemoval`` state and remain in the model.
        """
        log.trace.debug("Deleting Removed items from the model")
        states = set([ModelItem.Removed])
        removed_items = sorted(
            [item for item in self.data_manager.model.query_by_states(states)],
            key=lambda item: item.parent_vpath, reverse=True)
        collections = []

        for item in removed_items:
            if item.is_collection():
                collections.append(item)

            try:
                # This applies to collection items also!
                self._delete_removed_item(item)
            except ModelManagerException:
                # We couldn't remove 'item' because there are items in either
                # its progeny or references that were not transitioned to the
                # Removed state at the end of the plan. Reset it and its
                # children to ForRemoval.
                for child in item.children.values():
                    if child.is_removed():
                        self._set_item_for_removal(child)
                self._set_item_for_removal(item)

        # Restore all collections that shouldn't have been removed.
        for item in collections:
            parent = item.parent
            if parent:
                item.set_for_removal()
                self.data_manager.model.add(item)

    def _match_qparams_mitem(self, item, qparams):
        properties = item.get_merged_properties()
        for fieldname, value in qparams.iteritems():
            if fieldname not in properties:
                return False
            field = properties[fieldname]
            if field != value:
                return False
        return True

    def _match_qparams_qitem(self, item, qparams):
        item = QueryItem(self, item)
        for fieldname, expected_value in qparams.iteritems():
            actual_value = getattr(item, fieldname)
            if callable(actual_value):
                actual_value = actual_value()
            if actual_value != expected_value:
                return False
        return True

    def _match_qparams(self, item, qparams):
        mitem_properties = {}
        qitem_methods = {}

        item_type_properties = set([
            fname for fname, field in item.item_type.structure.iteritems()
            if isinstance(field, Property)
        ])
        for fieldname, value in qparams.iteritems():
            if fieldname in item_type_properties:
                mitem_properties[fieldname] = value
            elif hasattr(QueryItem, fieldname) \
                    and not fieldname.startswith("_"):
                qitem_methods[fieldname] = value
            else:
                # invalid
                return None

        if not self._match_qparams_mitem(item, mitem_properties):
            return None

        if not self._match_qparams_qitem(item, qitem_methods):
            return None

        return item

    def query_model_item(self, model_item, item_type_id, **properties):
        model_items = []
        for mitem in self.query_descends(model_item):
            item = self.get_matched_model_item(mitem, item_type_id, properties)
            if item:
                model_items.append(item)
        return model_items

    def query(self, item_type_id, **properties):
        """
        Return a list of ``ModelItem`` objects that match specified criteria.

        :param item_type_id: Item type name to be found.
        :type  item_type_id: str
        :param   properties: Structure of the item.
        :type    properties: dict

        """
        item_type_ids = set([item_type_id])
        if item_type_id in self.item_types:
            item_type_ids.update(
                self.model_dependency_helper.get_extending_types(
                    self.item_types[item_type_id]))
        result = []
        for item in self.data_manager.model.query_by_item_types(item_type_ids):
            if item.source_vpath:
                continue
            qitem = self.get_matched_model_item(item, item_type_id, properties)
            if qitem is not None:
                result.append(qitem)
        return result

    def query_all(self, **qparams):
        result = []
        for item in self.data_manager.model.query():
            qitem = self._match_qparams(item, qparams)
            if qitem is not None:
                result.append(qitem)
        return result

    def get_matched_model_item(self, item, item_type_id, properties):
        if (
            isinstance(item, (CollectionItem, RefCollectionItem)) or
            not item._extends(item_type_id)
        ):
            return None
        return self._match_qparams(item, properties)

    def query_by_vpath(self, vpath):
        """
        Return a ``ModelItem`` object specifing ``ModelItem``'s' URL.

        :param vpath: URL to the ``ModelItem``.
        :type  vpath: str

        """

        mitem = self.data_manager.model.get(vpath)
        if not mitem:
            raise ModelManagerException("Item %s not found" % vpath)
        return mitem

    def set_debug(self, force_debug, normal_start=False):
        '''
        Method for backwards compatibility see force_debug
        '''
        self.force_debug(force_debug, normal_start=normal_start)

    def force_debug(self, force_debug, normal_start=False):
        """Force DEBUG log level on or don't force it on.

        If the 'force_debug' parameter is True the log level will be set to
        DEBUG. Otherwise, the level will be set to whatever is specified in the
        config file.

        The 'normal_start' refers to the scenario where the log level is set at
        'service litpd start'. Here the level will be set to what is in the
        config file and, the 'force_debug' property of the logging ModelItem is
        set back to 'false' regardless of what level has been set.

        :param force_debug: Force DEBUG level on or not
        :type: force_debug: bool
        :param normal_start: Called as a result of starting the litpd service
        :type normal_start: bool
        """
        if force_debug and not normal_start:
            log.trace.setLevel(logging.DEBUG)
            return

        parser = SafeConfigParser()
        parser.read(LITP_LOG_CONF_FILE_PATH)
        error_message = ""
        if not parser.sections():
            error_message = "/etc/litp_logging.conf not found or is empty."
        elif not parser.has_section("logger_litptrace"):
            error_message = "missing logger_litptrace section"
        elif not parser.has_option("logger_litptrace", "level"):
            error_message = "missing level option"
        else:
            config_file_level_name = parser.get("logger_litptrace", "level")
            try:
                config_file_level_no = getattr(logging, config_file_level_name)
            except AttributeError:
                error_message = "%s is not a valid level option" % \
                        config_file_level_name

        if error_message:
            log.trace.info(error_message)
            return ValidationError(
                item_path='/litp/logging',
                error_message=error_message,
                error_type=constants.INTERNAL_SERVER_ERROR
            )

        log.trace.setLevel(config_file_level_no)
        if normal_start:
            self.update_item("/litp/logging", force_debug="false")

    def handle_upgrade_item(self, item_path, sha):
        """
        Will create/update upgrade items wherever it is necessary.
        :param item_path: URL to the ``ModelItem``.
        :type  item_path: str
        :param sha: Id of the upgrade.
        :type  sha: str
        """
        validation_err = ValidationError(
                       item_path=item_path,
                       error_message="Upgrade can only be run on deployments, "
                                     "clusters or nodes",
                       error_type=constants.INVALID_LOCATION_ERROR)
        item = self.query_by_vpath(item_path)
        if not item:
            return ValidationError(item_path=item_path,
                                   error_message="Path not found",
                                   error_type=constants.INVALID_LOCATION_ERROR)
        if not item.is_node() and \
           not item.is_cluster() and \
           not item.is_deployment() or \
           item.is_ms():
            return validation_err
        for node in iter(self._get_nodes_for_real(item)):
            if node.is_for_removal():
                continue
            result = self._process_upgradeitem_in_node(node, sha)
            if result and isinstance(result, list):
                # create_item returns something independently of it being the
                # created item or an error :(
                return result[0]

    def set_items_to_initial_from(self, item_path, exclude_paths=None):
        """
        Sets all model items apart from those in exclude_paths to Initial
        from the specified path.
        Also sets the model items applied_properties_determinable
        flag back to True.
        Returns a list of errors or None if it run successfully.

        :param item_path: URL to the ``ModelItem`` to be set to ``Initial``.
        :type item_path: str
        :param exclude_paths: list of ``item_path`` prefixes to
                              ignore under ``item_path``
        :type exclude_paths: list
        """
        errors = []
        if exclude_paths is None:
            exclude_paths = []

        item = self.query_by_vpath(item_path)

        if not item:
            return errors.append(
                ValidationError(
                    item_path=item_path,
                    error_message="Path not found",
                    error_type=constants.INVALID_LOCATION_ERROR
                ).to_dict()
            )

        item = self.get_item(item_path)
        error = self.check_item_exists(item, item_path)
        if error is not None:
            return errors.append(error.to_dict())

        self._set_items_to_initial(item, exclude_paths)

    def _get_nodes_for_real(self, item):
        # self.query_model_item will return an empty list if you run
        # query_model_item(item, 'node') on a node object, which is wrong
        # according to algebra rules.
        nodes = self.query_model_item(item, 'node')
        if item.item_type.item_type_id == 'node':
            nodes.append(item)
        return nodes

    def _process_upgradeitem_in_node(self, node, sha):
        if self.query_model_item(node, 'upgrade'):
            # it exists, just update
            model_item = self.query_model_item(node, 'upgrade')[0]
            model_item.update_properties({'hash': sha})
            for propname in ['requires_reboot', 'reboot_performed',
                             'disable_reboot', 'pre_os_reinstall',
                             'os_reinstall', 'ha_manager_only',
                             'redeploy_ms', 'infra_update']:
                try:
                    model_item.delete_property(propname)
                except AttributeError:
                    pass
        else:
            # doesn't exist, create'
            return self.create_item('upgrade',
                                    '/'.join([node.vpath, 'upgrade']),
                                    hash=sha)

    def check_model_item_deprecation(self, item):
        if item.is_collection():
            return
        self._check_type_deprecation(item.item_type, item.item_id, item.vpath)
        if item.parent_vpath:
            parent_structure = item.parent.item_type.structure
            if item.item_id in parent_structure:
                self._check_type_deprecation(
                    parent_structure[item.item_id], item.item_id, item.vpath)
        for prop in item.properties:
            if prop in item.item_type.structure:
                self._check_type_deprecation(
                    item.item_type.structure[prop], prop, item.vpath)
                property_type = item.item_type.structure[prop].prop_type
                if property_type:
                    self._check_type_deprecation(
                        property_type, prop, item.vpath)

    def _check_type_deprecation(self, item_type, item_id, item_vpath):
        if not item_type.deprecated:
            return
        if isinstance(item_type, PropertyType):
            log.trace.warning(
                "%s: '%s' used for Property '%s' at '%s' "
                "is marked for deprecation" % (
                    item_type.__class__.__name__,
                    item_type.property_type_id,
                    item_id, item_vpath
                )
            )
        elif isinstance(item_type, ItemType):
            log.trace.warning(
                "%s: '%s' used for '%s' at '%s' "
                "is marked for deprecation" % (
                    item_type.__class__.__name__,
                    item_type.item_type_id,
                    item_id, item_vpath
                )
            )
        elif isinstance(item_type, Property):
            log.trace.warning(
                "Property '%s' (of type '%s') set on '%s' "
                "is marked for deprecation" % (
                    item_id,
                    item_type.item_type_id,
                    item_vpath
                )
            )

    def _validate_model_item(self, item):
        return self.validator.validate_item_type(
            item.item_type, item, access=PROPERTY_READ)

    def get_ancestor(self, item, item_type_id):
        while item:
            if item.is_type(item_type_id):
                return item
            item = item.parent
        return None

    def get_node(self, item):
        while item:
            if item.is_node() and not item.is_ms():
                return item
            item = item.parent
        return None

    def get_ms(self, item):
        while item:
            if item.is_ms():
                return item
            item = item.parent
        return None

    def get_cluster(self, item):
        return self.get_ancestor(item, "cluster-base")

    def get_node_or_ms(self, item):
        return self.get_node(item) or self.get_ms(item)

    def has_item(self, vpath):
        return self.data_manager.model.exists(vpath)

    def get_root(self):
        return self.data_manager.model.get("/")

    def get_item(self, vpath):
        return self.data_manager.model.get(vpath)

    def get_source(self, item):
        if not item.source_vpath:
            return None
        return self.get_item(item.source_vpath)

    def get_parent(self, item):
        if not item.parent_vpath:
            return None
        return self.get_item(item.parent_vpath)

    def _item_might_have_children(self, item):
        if isinstance(item, (CollectionItem, RefCollectionItem)):
            return True
        for field in item.item_type.structure.itervalues():
            if not isinstance(field, (Property, View)):
                return True
        return False

    def get_children(self, parent):
        if not self._item_might_have_children(parent):
            return {}
        return dict([
            (item.item_id, item)
            for item in self.data_manager.model.query_children(parent)
        ])

    def count_children(self, parent):
        if not self._item_might_have_children(parent):
            return 0
        return self.data_manager.model.count_children(parent)

    def get_child(self, parent, item_id):
        if not self._item_might_have_children(parent):
            return None
        vpath = self.generate_path(parent.vpath if parent else None, item_id)
        return self.data_manager.model.get(vpath)

    def query_descends(self, item):
        if self._item_might_have_children(item):
            for descend in self.data_manager.model.query_descends(item):
                yield descend

    def query_model(self):
        for item in self.data_manager.model.query():
            yield item

    def get_plugin_updatable_items(self):
        plugin_updatable_types = set()
        for item_type in self.item_types.itervalues():
            for name, type_member in item_type.structure.iteritems():
                if not isinstance(type_member, Property):
                    continue
                if type_member.updatable_plugin:
                    plugin_updatable_types.add(item_type)
                    break

        plugin_updatable_items = set()
        for model_item in self.query_model():
            if type(model_item) is not ModelItem:
                continue
            for updatable_type in plugin_updatable_types:
                if self._is_type(
                        model_item.item_type.item_type_id,
                        updatable_type.item_type_id
                    ):
                    plugin_updatable_items.add(model_item.vpath)
                    break
        return plugin_updatable_items

    def get_all_nodes(self):
        item_type_ids = set()
        if "ms" in self.item_types:
            item_type_ids.add("ms")
            item_type_ids.update(
                self.model_dependency_helper.get_extending_types(
                    self.item_types["ms"]))
        if "node" in self.item_types:
            item_type_ids.add("node")
            item_type_ids.update(
                self.model_dependency_helper.get_extending_types(
                    self.item_types["node"]))

        return [
            item for item in self.data_manager.model.query_by_item_types(
                item_type_ids)
            if (
                type(item) is ModelItem and
                not item.source_vpath
            )
        ]

    def _node_left_locked(self):
        # XXX Can there be more than one Node item left locked? presumably not
        # as long as lock/unlock tasks are executed singly
        for node in self.query("node"):
            if node.is_locked == "true":
                return node

    def get_dependencies(self, vpaths):
        deps = {}
        for vpath in vpaths:
            deps[vpath] = \
                self.model_dependency_helper.get_filtered_deps(vpath, vpaths)
        return deps

    def _set_applied_properties_determinable(self, item_tasks):
        for vpath, tasks in item_tasks.iteritems():
            model_item = self.get_item(vpath)
            if not model_item:
                continue

            if any(task.state != constants.TASK_INITIAL for task in tasks):
                if any(task.state != constants.TASK_SUCCESS for task in tasks
                        if task.lock_type == 'type_other'):
                    model_item._set_applied_properties_determinable(False)
                elif model_item.is_for_removal() and model_item.was_removed():
                    model_item._set_applied_properties_determinable(False)
                else:
                    model_item._set_applied_properties_determinable(True)

    def backup_exists(self, model_id):
        return self.data_manager.model.backup_exists(model_id)

    def restore_backup(self, model_id):
        logging_item = self.get_item("/litp/logging")
        force_debug = logging_item.get_property("force_debug")

        exclude = set(["/snapshots"])
        ret = self.data_manager.model.restore_backup(model_id, exclude)

        logging_item = self.get_item("/litp/logging")
        logging_item.set_property("force_debug", force_debug)

        return ret


class ModelManager(ModelManagerNextGen):
    def __init__(self, *args, **kwargs):
        # TODO: remove inline imports!
        from litp.data.db_storage import DbStorage
        from litp.data.data_manager import DataManager
        from litp.data.constants import LIVE_MODEL_ID
        from litp.data.test_db_engine import get_engine

        db_storage = DbStorage(get_engine())
        db_storage.reset()

        session = db_storage.create_session()
        super(ModelManager, self).__init__(*args, **kwargs)
        data_manager = DataManager(session)
        data_manager.configure(self, LIVE_MODEL_ID)
        self.data_manager = data_manager
