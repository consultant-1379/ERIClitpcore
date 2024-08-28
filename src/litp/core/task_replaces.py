from litp.core.set_repeater import SetRepeater


def deserialize_task_replaces(deserialized_replaces):
    values = set()
    for sdep in deserialized_replaces:
        dep = None
        if sdep[0] == "c":
            dep = tuple([sdep[1], sdep[2]])
        if dep is None:
            continue
        values.add(dep)
    return values


class TaskReplaces(SetRepeater):
    @staticmethod
    def deserialize(fn_get_serialized):
        obj = TaskReplaces(fn_get_serialized)
        obj.populate_deserialized(deserialize_task_replaces(
            fn_get_serialized()))
        return obj

    def serialize(self, value):
        if isinstance(value, tuple) and len(value) == 2:
            value = tuple(["c", value[0], value[1]])
        else:
            value = tuple()
        return value
