from litp.data.sa.types.list_as_json_type import ListAsJSONType


class SetAsJSONType(ListAsJSONType):
    # pylint: disable=abstract-method

    def process_bind_param(self, value, dialect):
        if value is not None:
            value = list(value)
            value.sort()
        return ListAsJSONType.process_bind_param(self, value, dialect)

    def process_result_value(self, value, dialect):
        value_as_list = ListAsJSONType.process_result_value(
            self, value, dialect)
        return set(value_as_list)
