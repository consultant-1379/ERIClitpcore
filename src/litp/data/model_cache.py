from litp.core.litp_logging import LitpLogger
from litp.core.etlogger import ETLogger, et_logged

log = LitpLogger()
et_log = ETLogger(log.trace.debug, "ModelCache ET")


class IndexValues(object):
    def __init__(self):
        self._as_set = set()
        self._as_sorted_list = None

    def __len__(self):
        return len(self._as_set)

    def add(self, value):
        self._as_set.add(value)
        self._as_sorted_list = None

    def remove(self, value):
        self._as_set.remove(value)
        self._as_sorted_list = None

    def values(self):
        if self._as_sorted_list is None:
            self._as_sorted_list = sorted(self._as_set)
        return self._as_sorted_list


class Index(object):
    def __init__(self, fn_key, fn_value, fn_item_lookup):
        self._key_to_values = {}
        self._fn_key = fn_key
        self._fn_value = fn_value
        self._fn_item_lookup = fn_item_lookup

    def _add(self, key, value):
        if key not in self._key_to_values:
            self._key_to_values[key] = IndexValues()
        self._key_to_values[key].add(value)

    def _remove(self, key, value):
        self._key_to_values[key].remove(value)
        if not len(self._key_to_values[key]):
            del self._key_to_values[key]

    def _update(self, old_key, new_key, value):
        if old_key:
            self._remove(old_key, value)
        if new_key:
            self._add(new_key, value)

    def add(self, item):
        key = self._fn_key(item)
        if not key:
            return
        value = self._fn_value(item)
        self._add(key, value)

    def remove(self, item):
        key = self._fn_key(item)
        if not key:
            return
        value = self._fn_value(item)
        self._remove(key, value)

    def update(self, item, old_key, new_key):
        value = self._fn_value(item)
        self._update(old_key, new_key, value)

    def _itervalues(self, key):
        if key not in self._key_to_values:
            return iter([])
        return iter(self._key_to_values[key].values())

    def itervalues(self, key):
        return (self._fn_item_lookup(value) for value in self._itervalues(key))

    def count(self, key):
        if key not in self._key_to_values:
            return 0
        return len(self._key_to_values[key])

    def clear(self):
        self._key_to_values.clear()


class _Cache(object):
    def __init__(self):
        self.items = {}  # vpath -> ModelItem instance
        self.items_sorted = None

        fn_value = lambda item: item._vpath
        fn_item_lookup = lambda key: self.items[key]

        self.items_by_parent = Index(
            lambda item: item._parent_vpath, fn_value, fn_item_lookup)
        self.items_by_source = Index(
            lambda item: item._source_vpath, fn_value, fn_item_lookup)
        self.items_by_item_type = Index(
            lambda item: item._item_type_id, fn_value, fn_item_lookup)
        self.items_by_state = Index(
            lambda item: item._state, fn_value, fn_item_lookup)
        self.indexes = [
            self.items_by_parent,
            self.items_by_source,
            self.items_by_item_type,
            self.items_by_state
        ]


class ModelCache(object):
    def __init__(self, model_data_manager):
        self._model_data_manager = model_data_manager

        self._cache = _Cache()
        self._load_model()

    def close(self):
        self.invalidate_cache()

    def _update_index(self, index, item, value, old_value):
        if type(value) == type(old_value) and value == old_value:
            return
        if item._vpath not in self._cache.items:
            return
        index.update(item, old_value, value)

    def on_parent_vpath_set(self, item, value, old_value, *args):
        self._update_index(
            self._cache.items_by_parent, item, value, item._parent_vpath)

    def on_source_vpath_set(self, item, value, old_value, *args):
        self._update_index(
            self._cache.items_by_source, item, value, item._source_vpath)

    def on_item_type_id_set(self, item, value, old_value, *args):
        self._update_index(
            self._cache.items_by_item_type, item, value, item._item_type_id)

    def on_state_set(self, item, value, old_value, *args):
        self._update_index(
            self._cache.items_by_state, item, value, item._state)

    def _add_to_indexes(self, item):
        for index in self._cache.indexes:
            index.add(item)

    def _remove_from_indexes(self, item):
        for index in self._cache.indexes:
            index.remove(item)

    def _cache_item(self, item):
        key = item._vpath
        if key in self._cache.items:
            self._uncache_item(self._cache.items[key])
        item.register_model_cache_instance(self)
        self._cache.items[key] = item
        self._cache.items_sorted = None
        self._add_to_indexes(item)

    def _uncache_item(self, item):
        key = item._vpath
        if key not in self._cache.items:
            return
        item.unregister_model_cache_instance(self)
        del self._cache.items[key]
        self._cache.items_sorted = None
        self._remove_from_indexes(item)

    @et_logged(et_log)
    def _load_model(self):
        log.trace.debug("[ModelCache] _load_model")
        for item in self._model_data_manager.query():
            self._cache_item(item)

    def invalidate_cache(self):
        for item in self._cache.items.itervalues():
            item.unregister_model_cache_instance(self)
        self._cache.items.clear()
        for index in self._cache.indexes:
            index.clear()

    def exists(self, vpath):
        return self._cache.items.get(vpath) is not None

    def get(self, vpath):
        return self._cache.items.get(vpath)

    def add(self, item):
        item = self._model_data_manager.add(item)
        self._cache_item(item)
        return item

    def delete(self, item):
        item = self._model_data_manager.delete(item)
        self._uncache_item(item)
        return item

    def _query_descends(self, parent):
        for child in self._cache.items_by_parent.itervalues(parent._vpath):
            yield child
            for grandchild in self._query_descends(child):
                yield grandchild

    def query_descends(self, parent):
        log.trace.debug(
            "[ModelCache] query_descends, parent=%s",
            parent.vpath)
        return self._query_descends(parent)

    def count_children(self, parent):
        log.trace.debug(
            "[ModelCache] count_children, parent=%s",
            parent.vpath)
        return self._cache.items_by_parent.count(parent._vpath)

    def query_children(self, parent):
        log.trace.debug(
            "[ModelCache] query_children, parent=%s",
            parent.vpath)
        return self._cache.items_by_parent.itervalues(parent._vpath)

    def query_inherited(self, source):
        log.trace.debug(
            "[ModelCache] query_inherited, source=%s",
            source.vpath)
        return self._cache.items_by_source.itervalues(source._vpath)

    def query_by_item_types(self, item_type_ids):
        log.trace.debug(
            "[ModelCache] query_by_item_types, "
            "item_type_ids=%s", item_type_ids)
        ret = []
        for item_type_id in item_type_ids:
            ret.extend(self._cache.items_by_item_type.itervalues(item_type_id))
        ret.sort(key=lambda x: x._vpath)
        return iter(ret)

    def query_by_states(self, states):
        log.trace.debug(
            "[ModelCache] query_by_states, states=%s",
            states)
        ret = []
        for state in states:
            ret.extend(self._cache.items_by_state.itervalues(state))
        ret.sort(key=lambda x: x._vpath)
        return iter(ret)

    def query(self):
        log.trace.debug("[ModelCache] query")
        if self._cache.items_sorted is None:
            self._cache.items_sorted = self._cache.items.values()
            self._cache.items_sorted.sort(key=lambda x: x._vpath)
        return iter(self._cache.items_sorted)
