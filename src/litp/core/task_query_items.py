from litp.core.set_repeater import SetRepeater
from litp.core.model_manager import QueryItem


def deserialize_task_query_items(deserialized_query_items, model_manager):
    values = set()
    for vpath in deserialized_query_items:
        item = model_manager.get_item(vpath)
        if not item:
            continue
        item = QueryItem(model_manager, item)
        values.add(item)
    return values


class TaskQueryItems(SetRepeater):
    @staticmethod
    def deserialize(fn_get_serialized, model_manager):
        obj = TaskQueryItems(fn_get_serialized)
        obj.populate_deserialized(deserialize_task_query_items(
            fn_get_serialized(), model_manager))
        return obj

    def serialize(self, value):
        try:
            value = value.vpath
        except AttributeError:
            pass
        return value
