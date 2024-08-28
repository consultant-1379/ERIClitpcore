from litp.data.sa.types.json_type import JSONType


class CollectionAsJSONType(JSONType):
    # pylint: disable=abstract-method

    def __init__(self, serialize_empty_as=None, deserialize_empty_as=None):
        JSONType.__init__(self)
        self._serialize_empty_as = serialize_empty_as
        self._deserialize_empty_as = deserialize_empty_as

    def process_bind_param(self, value, dialect):
        if not value:
            if self._serialize_empty_as is None:
                ret = None
            else:
                ret = self._serialize_empty_as()
        else:
            ret = JSONType.process_bind_param(self, value, dialect)
        return ret

    def process_result_value(self, value, dialect):
        if value is None:
            if self._deserialize_empty_as is None:
                ret = None
            else:
                ret = self._deserialize_empty_as()
        else:
            ret = JSONType.process_result_value(self, value, dialect)
        return ret
