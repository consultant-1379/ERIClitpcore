class ListRepeater(list):
    def __init__(self, fn_get_serialized, *args):
        list.__init__(self)
        self._fn_get_serialized = fn_get_serialized
        if len(args):
            self.extend(args[0])

    def serialize(self, item):
        raise NotImplementedError

    def populate_deserialized(self, values):
        list.extend(self, values)

    def __setitem__(self, index, value):
        self._fn_get_serialized().__setitem__(index, self.serialize(value))
        return list.__setitem__(self, index, value)

    def __setslice__(self, start, end, value):
        self._fn_get_serialized().__setslice__(
            start, end, self.serialize(value))
        return list.__setslice__(self, start, end, value)

    def __delitem__(self, index):
        self._fn_get_serialized().__delitem__(index)
        return list.__delitem__(self, index)

    def __delslice__(self, start, end):
        self._fn_get_serialized().__delslice__(start, end)
        return list.__delslice__(self, start, end)

    def pop(self, *args):
        self._fn_get_serialized().pop(*args)
        return list.pop(self, *args)

    def append(self, value):
        self._fn_get_serialized().append(self.serialize(value))
        return list.append(self, value)

    def extend(self, values):
        self._fn_get_serialized().extend(
            [self.serialize(value) for value in values])
        return list.extend(self, values)

    def insert(self, index, value):
        self._fn_get_serialized().insert(index, self.serialize(value))
        return list.insert(self, index, value)

    def remove(self, index):
        self._fn_get_serialized().remove(index)
        return list.remove(self, index)

    def sort(self):
        self._fn_get_serialized().sort()
        return list.sort(self)

    def reverse(self):
        self._fn_get_serialized().reverse()
        return list.reverse(self)
