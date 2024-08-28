LAZY_PROPERTY_PREFIX = "_lazy_"


def lazy_property(fn):
    attr_name = LAZY_PROPERTY_PREFIX + fn.__name__

    def _getx(self):
        if not hasattr(self, attr_name):
            setattr(self, attr_name, fn(self))
        return getattr(self, attr_name)

    def _setx(self, attr_value):
        setattr(self, attr_name, attr_value)

    def _delx(self):
        delattr(self, attr_name)

    return property(_getx, _setx, _delx)


def delete_lazy_properties(obj):
    for attr_name in obj.__dict__.keys():
        if not attr_name.startswith(LAZY_PROPERTY_PREFIX):
            continue
        delattr(obj, attr_name)
