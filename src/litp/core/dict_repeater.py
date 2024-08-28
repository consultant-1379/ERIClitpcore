class DictRepeater(dict):
    def __init__(self, fn_get_serialized, *args, **kwargs):
        dict.__init__(self)
        self._fn_get_serialized = fn_get_serialized
        if len(args):
            self.update(args[0])
        if kwargs:
            self.update(kwargs)

    def serialize(self, item):
        raise NotImplementedError

    def populate_deserialized(self, values):
        dict.update(self, values)

    def __setitem__(self, key, value):
        self._fn_get_serialized().__setitem__(key, self.serialize(value))
        return dict.__setitem__(self, key, value)

    def __delitem__(self, key):
        self._fn_get_serialized().__delitem__(key)
        return dict.__delitem__(self, key)

    def setdefault(self, key, value):
        self._fn_get_serialized().setdefault(key, self.serialize(value))
        return dict.setdefault(self, key, value)

    def update(self, *args, **kwargs):
        dicts = []
        for d in args:
            serialized = dict(d)
            for key, value in serialized.iteritems():
                serialized[key] = self.serialize(value)
            self._fn_get_serialized().update(serialized)
            dict.update(self, d)

    def pop(self, *args):
        self._fn_get_serialized().pop(*args)
        return dict.pop(self, *args)

    def popitem(self):
        self._fn_get_serialized().popitem()
        return dict.popitem(self)

    def clear(self):
        self._fn_get_serialized().clear()
        return dict.clear(self)
