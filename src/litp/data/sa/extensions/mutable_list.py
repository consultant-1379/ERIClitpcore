from sqlalchemy.ext.mutable import Mutable


class MutableList(Mutable, list):
    @classmethod
    def coerce(cls, _key, value):
        if isinstance(value, list):
            obj = MutableList(value)
        elif isinstance(value, MutableList):
            obj = value
        else:
            raise ValueError("invalid value: %s" % value)
        return obj

    def __repr__(self):
        return repr([str(x) for x in self])

    def __getattribute__(self, name):
        value = super(MutableList, self).__getattribute__(name)
        if callable(value) and getattr(list, name, None):
            value = self._wrap_method(value)
        return value

    def _wrap_method(self, method):
        def wrapped_method(*args, **kwargs):
            ret = method(*args, **kwargs)
            self.changed()
            return ret
        return wrapped_method
