class SetRepeater(set):
    def __init__(self, fn_get_serialized, *args):
        set.__init__(self)
        self._fn_get_serialized = fn_get_serialized
        if len(args):
            self.update(args[0])

    def serialize(self, item):
        raise NotImplementedError

    def populate_deserialized(self, values):
        set.update(self, values)

    def update(self, *args):
        for values in args:
            self._fn_get_serialized().update(
                [self.serialize(value) for value in values])
            set.update(self, values)

    def intersection_update(self, *args):
        for values in args:
            self._fn_get_serialized().intersection_update(
                [self.serialize(value) for value in values])
            set.intersection_update(self, values)

    def difference_update(self, *args):
        for values in args:
            self._fn_get_serialized().difference_update(
                [self.serialize(value) for value in values])
            set.difference_update(self, values)

    def symmetric_difference_update(self, *args):
        for values in args:
            self._fn_get_serialized().symmetric_difference_update(
                [self.serialize(value) for value in values])
            set.symmetric_difference_update(self, values)

    def add(self, value):
        self._fn_get_serialized().add(self.serialize(value))
        return set.add(self, value)

    def remove(self, value):
        self._fn_get_serialized().remove(self.serialize(value))
        return set.remove(self, value)

    def discard(self, value):
        self._fn_get_serialized().discard(self.serialize(value))
        return set.discard(self, value)

    def pop(self):
        value = set.pop(self)
        try:
            self._fn_get_serialized().remove(self.serialize(value))
        except (ValueError, KeyError):
            set.add(self, value)
            raise
        return value

    def clear(self):
        self._fn_get_serialized().clear()
        return set.clear(self)
