from litp.data.sa.types.collection_as_json_type import CollectionAsJSONType


class ListAsJSONType(CollectionAsJSONType):
    # pylint: disable=abstract-method

    def __init__(self):
        CollectionAsJSONType.__init__(self, deserialize_empty_as=list)
