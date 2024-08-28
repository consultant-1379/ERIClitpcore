from litp.data.base_model_data_manager import BaseModelDataManager
from litp.data.types import GeneratorType


class ModelDataManager(BaseModelDataManager):
    def __init__(self, *args, **kwargs):
        super(ModelDataManager, self).__init__(*args, **kwargs)

        self._cached_items = {}
        self._cached_queries = {}

    def _cached(self, key, fn, *args, **kwargs):
        if key in self._cached_queries:
            cached = self._cached_queries[key]
        else:
            cached = fn(*args, **kwargs)
            if isinstance(cached, GeneratorType):
                cached = list(cached)
            self._cached_queries[key] = cached
            if isinstance(cached, list):
                self._cache_all_items(cached)

        if isinstance(cached, list):
            ret = list(cached)
        else:
            ret = cached

        return ret

    def _cache_all_items(self, items):
        for item in items:
            self._cache_item(item)

    def _cache_nonexistent_item(self, vpath):
        self._cached_items[vpath] = None

    def _cache_item(self, item):
        if (
            item._vpath in self._cached_items and
            self._cached_items[item._vpath] is not None
        ):
            return
        item.register_model_data_manager_instance(self)
        self._cached_items[item._vpath] = item

    def _uncache_item(self, item):
        if item._vpath not in self._cached_items:
            return
        item.unregister_model_data_manager_instance(self)
        del self._cached_items[item._vpath]

    def invalidate_cache(self):
        for item in self._cached_items.itervalues():
            if item is None:
                continue
            item.unregister_model_data_manager_instance(self)
        self._cached_items.clear()
        self._cached_queries.clear()

    def on_attribute_set(self, *args, **kwargs):
        self._cached_queries.clear()

    def close(self, *args, **kwargs):
        self.invalidate_cache()

        return super(
            ModelDataManager, self).close(*args, **kwargs)

    def create_backup(self, *args, **kwargs):
        self.invalidate_cache()
        return super(
            ModelDataManager, self).create_backup(*args, **kwargs)

    def delete_backup(self, *args, **kwargs):
        self.invalidate_cache()
        return super(
            ModelDataManager, self).delete_backup(*args, **kwargs)

    def restore_backup(self, *args, **kwargs):
        self.invalidate_cache()
        return super(
            ModelDataManager, self).restore_backup(*args, **kwargs)

    def exists(self, vpath):
        item = self.get(vpath)
        return item is not None

    def get(self, vpath):
        if vpath in self._cached_items:
            return self._cached_items[vpath]
        item = super(ModelDataManager, self).get(vpath)
        if item is None:
            self._cache_nonexistent_item(vpath)
        else:
            self._cache_item(item)
        return item

    def add(self, item):
        item = super(ModelDataManager, self).add(item)
        self._cached_queries.clear()
        self._cache_item(item)
        return item

    def delete(self, item):
        item = super(ModelDataManager, self).delete(item)
        self._cached_queries.clear()
        self._uncache_item(item)
        return item

    def query_descends(self, parent):
        key = "query_descends:%s" % parent._vpath
        return self._cached(
            key, super(ModelDataManager, self).query_descends,
            parent)

    def count_children(self, parent):
        key = "count_children:%s" % parent._vpath
        return self._cached(
            key, super(ModelDataManager, self).count_children,
            parent)

    def query_children(self, parent):
        key = "query_children:%s" % parent._vpath
        return self._cached(
            key, super(ModelDataManager, self).query_children,
            parent)

    def query_inherited(self, source):
        key = "query_inherited:%s" % source._vpath
        return self._cached(
            key, super(ModelDataManager, self).query_inherited,
            source)

    def query_by_item_types(self, item_type_ids):
        key = "query_by_item_types:%s" % sorted(list(item_type_ids))
        return self._cached(
            key, super(ModelDataManager, self).query_by_item_types,
            item_type_ids)

    def query_by_states(self, states):
        key = "query_by_states:%s" % sorted(list(states))
        return self._cached(
            key, super(ModelDataManager, self).query_by_states,
            states)

    def query(self):
        key = "query"
        return self._cached(
            key, super(ModelDataManager, self).query)
