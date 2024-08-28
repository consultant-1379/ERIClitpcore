from litp.core.list_repeater import ListRepeater
from litp.core.task_utils import serialize_arg_value_from_object
from litp.core.task_utils import deserialize_arg_value_to_object


def deserialize_task_args(deserialized_args, model_manager):
    return [
        deserialize_arg_value_to_object(value, model_manager)
        for value in deserialized_args
    ]


class TaskArgs(ListRepeater):
    @staticmethod
    def deserialize(fn_get_serialized, model_manager):
        obj = TaskArgs(fn_get_serialized)
        obj.populate_deserialized(
            deserialize_task_args(fn_get_serialized(), model_manager))
        return obj

    def serialize(self, value):
        return serialize_arg_value_from_object(value)
