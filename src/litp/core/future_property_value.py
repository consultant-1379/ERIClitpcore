from litp.core.model_type import View


class FuturePropertyValue(object):
    """Allows a property's value to be evaluated during a running plan."""

    def __init__(self, query_item, property_name):
        self.query_item = query_item
        self.property_name = property_name

    def __cmp__(self, rhs):
        # Priority: 1. value, 2. query_item, 3. property_name
        if isinstance(rhs, FuturePropertyValue):
            if cmp(self.value, rhs.value) == 0:
                if cmp(self.query_item, rhs.query_item) == 0:
                    return cmp(self.property_name, rhs.property_name)
                return cmp(self.query_item, rhs.query_item)
            return cmp(self.value, rhs.value)
        return cmp(self.value, rhs)

    @property
    def value(self):
        return getattr(self.query_item, self.property_name)

    def is_updatable_plugin(self):
        if self.get_property().updatable_plugin:
            return True
        return False

    def is_view(self):
        if isinstance(self.get_property(), View):
            return True
        return False

    def get_property(self):
        return self.query_item._model_item._item_type.structure[
                    self.property_name]
