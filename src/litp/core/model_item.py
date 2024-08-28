##############################################################################
# COPYRIGHT Ericsson AB 2013
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################


from sqlalchemy import event

from litp.core.litp_logging import LitpLogger
from litp.core.model_type import Property
from litp.core.model_type import View
from litp.data.constants import LIVE_MODEL_ID
from litp.data.types import Base as DbBase
from litp.data.types import ModelItem as DbModelItem

log = LitpLogger()


class ModelItem(DbModelItem, DbBase):
    # pylint: disable=attribute-defined-outside-init
    """ Basic item that represents a state of an Item within a model.  """
    def __init__(self, model_manager, item_type, item_id, parent_vpath,
                 properties=None):
        if properties is None:
            properties = dict()

        self._model_id = LIVE_MODEL_ID
        self._model_manager = model_manager
        self._item_type_id = item_type.item_type_id
        self._item_id = item_id
        self._parent_vpath = parent_vpath
        self._vpath = self._construct_vpath()
        self._source_vpath = None
        self._properties = properties
        self._applied_properties = dict()
        self._state = ModelItem.Initial
        self._previous_state = None
        self.applied_properties_determinable = True
        self._init_attributes()

    def initialize_from_db(self, model_manager):
        if getattr(self, "_initialized", False):
            return
        self._model_manager = model_manager
        self._init_attributes()

    def _init_attributes(self):
        self._initialized = True
        self._model_data_manager_instances = set()
        self._model_cache_instances = set()

    @property
    def model_data_manager_instances(self):
        return self._model_data_manager_instances

    def register_model_data_manager_instance(self, instance):
        self._model_data_manager_instances.add(instance)

    def unregister_model_data_manager_instance(self, instance):
        self._model_data_manager_instances.remove(instance)

    @property
    def model_cache_instances(self):
        return self._model_cache_instances

    def register_model_cache_instance(self, instance):
        self._model_cache_instances.add(instance)

    def unregister_model_cache_instance(self, instance):
        self._model_cache_instances.remove(instance)

    def __getattr__(self, name):
        if (
            name.startswith("_sa") or
            name == "_initialized"
        ):
            raise AttributeError()

        if name in self.item_type.structure:
            struct_member = self.item_type.structure[name]
            if isinstance(struct_member, Property):
                value = self._properties.get(name)
            elif isinstance(struct_member, View):
                value = struct_member.callable_method
            else:
                value = self.get_child(name)
            return value

        if isinstance(self, (CollectionItem, RefCollectionItem)):
            child = self.get_child(name)
            if child:
                return child

        raise AttributeError(
            "No such field %s in %s" % (name, self.item_type)
        )

    def __repr__(self):
        return "<%s %s type=%s state=%s>" % (
            self.__class__.__name__, self.vpath,
            self.item_type_id, self._state
        )

    def _build_item_comparison_dict(self):
        return {
            "vpath": self._vpath,
            "properties": self._properties,
            "state": self._state,
            "item_type_id": self._item_type_id,
            "parent_vpath": self._parent_vpath,
            "source_vpath": self._source_vpath,
        }

    def __hash__(self):
        return hash(self.vpath)

    def __eq__(self, other):
        if type(self) is type(other):
            return self._build_item_comparison_dict() == \
                other._build_item_comparison_dict()
        return NotImplemented

    def __ne__(self, other):
        if type(self) is type(other):
            return not self.__eq__(other)
        return NotImplemented

    def __iter__(self):
        for model_item in self.children.itervalues():
            yield model_item

    def __len__(self):
        if not isinstance(self, (CollectionItem, RefCollectionItem)):
            return 0
        return self._model_manager.count_children(self)

    def __nonzero__(self):
        return True

    @property
    def vpath(self):
        return self._vpath

    @property
    def item_id(self):
        return self._item_id

    @property
    def item_type_id(self):
        return self._item_type_id

    @property
    def item_type(self):
        return self._model_manager.item_types[self._item_type_id]

    @property
    def _item_type(self):
        return self.item_type

    @_item_type.setter
    def _item_type(self, item_type):
        self._item_type_id = item_type.item_type_id

    @property
    def _require(self):
        if not self.parent:
            return None
        if isinstance(self.parent, (CollectionItem, RefCollectionItem)):
            return None
        return self.parent.item_type.structure[self.item_id]._require

    @property
    def parent_vpath(self):
        return self._parent_vpath

    @property
    def source_vpath(self):
        return self._source_vpath

    @source_vpath.setter
    def source_vpath(self, value):
        self._source_vpath = value

    @property
    def parent(self):  # pylint: disable=method-hidden
        return self._model_manager.get_parent(self)

    @property
    def children(self):
        return self._model_manager.get_children(self)

    @property  # pylint: disable=method-hidden
    def source(self):
        return self._model_manager.get_source(self)

    @property
    def properties(self):
        return self._properties

    @properties.setter
    def properties(self, value):
        # NOTE: only UTs use this
        self._properties = value

    @property
    def applied_properties(self):
        return self._applied_properties

    @applied_properties.setter
    def applied_properties(self, value):
        # NOTE: only UTs use this
        self._applied_properties = value

    @property
    def state(self):
        return self._state

    @state.setter
    def state(self, value):
        self._state = value

    @property
    def previous_state(self):
        return self._previous_state

    @previous_state.setter
    def previous_state(self, value):
        self._previous_state = value

    def _construct_vpath(self):
        if not self._item_id:
            vpath = "/"
        elif not self._parent_vpath or self._parent_vpath == "/":
            vpath = "/" + self._item_id
        else:
            vpath = self._parent_vpath + "/" + self._item_id
        return vpath

    @property
    def _inheritance_chain(self):
        items = []
        item = self
        while item:
            items.append(item)
            item = self._model_manager.get_item(item.source_vpath) \
                    if item.source_vpath else None
        return items

    def get_merged_properties(self, skip_views=False):
        properties = {}
        for item in self._inheritance_chain:
            for name, value in item.iterate_properties(skip_views):
                if name in properties:
                    continue
                properties[name] = value
        return properties

    def get_non_config_properties(self, properties):
        return dict((name, value) for (name, value) in properties.iteritems()
                    if name in self.item_type.structure and
                    not self.item_type.structure[name].configuration)

    def update_properties(self, properties):
        if not properties:
            return
        # non config props are applied immediately, then do normal update
        non_config_applied = self.apply_non_config_properties(properties)
        for name, value in properties.iteritems():
            self.set_property(name, value)

        applied_properties = self.get_applied_properties(skip_views=True)
        merged_properties = self.get_merged_properties(skip_views=True)

        if (
            (self.is_applied() or self.is_for_removal()) and
            applied_properties != merged_properties
        ):
            self.set_updated()

        elif (
            self.is_updated() and self.applied_properties_determinable and
            applied_properties == merged_properties and
            self._previous_state in (ModelItem.Applied, ModelItem.Updated)
        ):
            self.set_applied()

        elif (self.is_for_removal() and non_config_applied and
            self.previous_state in (ModelItem.Applied, ModelItem.Updated)
        ):
            self.state = self.previous_state

    def apply_non_config_properties(self, properties, overwrite=True):
        """
        Look for non-configuration properties and set them straight to applied.
        Overwrite inherited properties when updating the item directly, but
        allow to skip them for recursive updates.
        """
        non_conf_props = self.get_non_config_properties(properties)
        applied_properties = self.get_applied_properties(skip_views=True)

        non_config_applied = False
        for name, value in non_conf_props.iteritems():
            if not overwrite and self.is_property_overwritten(name):
                continue

            if (name not in applied_properties or
                applied_properties[name] != value
            ):
                # set only the applied property value, normal property
                # should only be updated in update_properties() above
                self.set_property(name, value, to_applied=True)
            non_config_applied = True

        return non_config_applied

    def get_child(self, item_id):
        return self._model_manager.get_child(self, item_id)

    def get_state(self):
        return self._state

    def get_vpath(self):
        return self.vpath

    def is_collection(self):
        if isinstance(self, (CollectionItem, RefCollectionItem)):
            return True
        return False

    def _set_applied_properties_determinable(self, new_value):
        if self.applied_properties_determinable != new_value:
            self.applied_properties_determinable = new_value

    def _set_state(self, new_state):
        if new_state == ModelItem.Applied:
            self._set_applied_properties_determinable(True)

        if self._state != new_state:
            if self._state != ModelItem.ForRemoval:
                self._previous_state = self._state

            self._state = new_state
            if new_state == ModelItem.Applied:
                self._applied_properties = self.get_merged_properties()

    def set_initial(self):
        self._set_state(ModelItem.Initial)

    def set_updated(self):
        self._set_state(ModelItem.Updated)

    def set_applied(self):
        self._set_state(ModelItem.Applied)

    def set_for_removal(self):
        self._set_state(ModelItem.ForRemoval)

    def set_removed(self):
        self._set_state(ModelItem.Removed)

    def set_state_child_collection(self):
        for child in self.children.values():
            if child.is_collection():
                child._set_state(self._state)

    def set_previous_state(self):
        # If APD is False, prevent item from going back to Applied
        if not self.applied_properties_determinable and \
                self.is_for_removal() and self.was_applied():
            self.set_updated()
        else:
            state = self._previous_state
            if state is None:
                state = ModelItem.Initial
            self._set_state(state)

    def is_initial(self):
        return self._state == ModelItem.Initial

    def is_applied(self):
        return self._state == ModelItem.Applied

    def was_applied(self):
        return self._previous_state == ModelItem.Applied

    def was_removed(self):
        return self._previous_state == ModelItem.Removed

    def was_initial(self):
        return self._previous_state == ModelItem.Initial

    def is_updated(self):
        return self._state == ModelItem.Updated

    def is_for_removal(self):
        return self._state == ModelItem.ForRemoval

    def is_removed(self):
        return self._state == ModelItem.Removed

    def is_instance(self, item_type_id):
        return self._extends(item_type_id)

    def is_type(self, item_type_id):
        return type(self) is ModelItem and self._extends(item_type_id)

    def _extends(self, item_type_id):
        if item_type_id == self.item_type_id:
            return True
        if item_type_id not in self._model_manager.item_types:
            return False
        mdh = self._model_manager.model_dependency_helper
        extended_item_ids = mdh.get_extending_types(
            self._model_manager.item_types[item_type_id])
        return self.item_type_id in extended_item_ids

    @property
    def has_overwritten_properties(self):
        """Has a inherited item overwritten a property from its source"""
        if self.source and self.properties:
            return True
        return False

    def is_property_overwritten(self, property_name):
        """Has a specific property of an inhertied item been overwritten"""
        if self.has_overwritten_properties:
            return property_name in self.properties
        return False

    def all_properties_overwritten(self, properties):
        """Have specified properties been overwritten on the inherited item"""
        if not properties:
            return False
        return all(self.is_property_overwritten(property_name)
                for property_name in properties)

    def set_property(self, name, value, to_applied=False):
        """If to_applied is True then only update the applied property"""
        if name.startswith('^') or value is None:
            self.delete_property(name, to_applied)
        else:
            if type(value) not in set([str, unicode]):
                raise ValueError("Invalid property value: %s" % repr(value))
            instance = self.item_type.structure.get(name)
            if not (instance and isinstance(instance, Property)):
                raise ValueError("Invalid property: %s", name)
            if not to_applied:
                self._properties[name] = value
            elif not self.is_initial():
                self._applied_properties[name] = value

    def delete_property(self, name, to_applied=False):
        """If to_applied is True then only delete the applied property"""
        instance = self.item_type.structure.get(name)
        if instance and not isinstance(instance, Property):
            instance = None

        has_default = (not self.source_vpath and
                instance and instance.required and instance.default)

        if name in self._properties and not to_applied:
            if has_default:
                self._properties[name] = instance.default
            else:
                del self._properties[name]

        # this is relevant only to non-configuration properties, set directly
        # to applied properties without setting the item to Updated state
        if name in self._applied_properties and to_applied:
            if self.source and name in self.source.properties:
                # inherited property, reset to value from source
                self._applied_properties[name] = self.source.properties[name]
            elif has_default:
                self._applied_properties[name] = instance.default
            else:
                del self._applied_properties[name]

    def get_property(self, name):
        instance = self.item_type.structure.get(name)
        if not (instance and isinstance(instance, Property)):
            raise ValueError("Invalid property: %s", name)
        return self.properties.get(name)

    def iterate_properties(self, skip_views):
        for name, value in self._properties.iteritems():
            if skip_views and callable(value):
                continue
            yield name, value

    def get_properties(self, skip_views=False):
        properties = {}
        for name, value in self.iterate_properties(skip_views):
            properties[name] = value
        return properties

    def get_applied_properties(self, skip_views=False):
        properties = {}
        for name, value in self._applied_properties.iteritems():
            if skip_views and callable(value):
                continue
            properties[name] = value
        return properties

    def reset_applied_properties(self):
        self._applied_properties = {}

    def show_item(self):
        return {
            "item_id": self.item_id,
            "item_type": self.item_type_id,
            "status": self._state,
            "properties": self.properties,
        }

    def is_node(self):
        return (
            type(self) is ModelItem and
            (self._extends("node") or self._extends("ms"))
        )

    def is_ms(self):
        return self.is_node() and self.item_type_id == "ms"

    def is_cluster(self):
        return self.is_type("cluster-base")

    def is_deployment(self):
        return self.is_type("deployment")

    def _properties_match(self, properties):
        for item in properties.iteritems():
            if not item in self._properties.iteritems():
                return False
        return True


class CollectionItem(ModelItem):
    def show_item(self):
        return {
            "item_id": self.item_id,
            "item_type": self.item_type_id,
            "status": self._state,
            "contained_type": self.item_type_id,
        }


class RefCollectionItem(ModelItem):
    pass


def _on_attribute_set(model_cache_method_name, item, value, old_value, *args):
    if not getattr(item, "_initialized", False):
        return
    for model_cache in item.model_cache_instances:
        method = getattr(model_cache, model_cache_method_name)
        method(item, value, old_value)
    for model_data_manager in item.model_data_manager_instances:
        model_data_manager.on_attribute_set(item, value, old_value)


def _on_parent_vpath_set(item, value, old_value, *args):
    _on_attribute_set("on_parent_vpath_set", item, value, old_value, *args)


def _on_source_vpath_set(item, value, old_value, *args):
    _on_attribute_set("on_source_vpath_set", item, value, old_value, *args)


def _on_item_type_id_set(item, value, old_value, *args):
    _on_attribute_set("on_item_type_id_set", item, value, old_value, *args)


def _on_state_set(item, value, old_value, *args):
    _on_attribute_set("on_state_set", item, value, old_value, *args)


event.listen(
    ModelItem._parent_vpath, "set", _on_parent_vpath_set, propagate=True)
event.listen(
    ModelItem._source_vpath, "set", _on_source_vpath_set, propagate=True)
event.listen(
    ModelItem._item_type_id, "set", _on_item_type_id_set, propagate=True)
event.listen(
    ModelItem._state, "set", _on_state_set, propagate=True)
