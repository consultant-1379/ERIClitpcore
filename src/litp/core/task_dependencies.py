from litp.core.set_repeater import SetRepeater
from litp.core.model_manager import QueryItem


def deserialize_task_dependencies(
        deserialized_dependencies, data_manager, model_manager):
    values = set()
    for sdep in deserialized_dependencies:
        dep = None
        if sdep[0] == "t":
            dep = data_manager.get_task_by_unique_id(sdep[1])
        elif sdep[0] == "q":
            dep = model_manager.get_item(sdep[1])
            if dep:
                dep = QueryItem(model_manager, dep)
        elif sdep[0] == "c":
            dep = tuple([sdep[1], sdep[2]])
        if dep is None:
            continue
        values.add(dep)
    return values


class TaskDependencies(SetRepeater):
    @staticmethod
    def deserialize(fn_get_serialized, data_manager, model_manager):
        obj = TaskDependencies(fn_get_serialized)
        obj.populate_deserialized(deserialize_task_dependencies(
            fn_get_serialized(), data_manager, model_manager))
        return obj

    def serialize(self, value):
        if isinstance(value, tuple) and len(value) == 2:
            value = tuple(["c", value[0], value[1]])
        elif hasattr(value, "unique_id"):
            value = tuple(["t", value.unique_id])
        elif hasattr(value, "vpath"):
            value = tuple(["q", value.vpath])
        else:
            value = tuple()
        return value
