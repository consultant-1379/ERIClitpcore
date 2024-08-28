from litp.core.dict_repeater import DictRepeater
from litp.core.task_utils import serialize_arg_value_from_object
from litp.core.task_utils import deserialize_arg_value_to_object


def deserialize_task_kwargs(deserialized_kwargs, model_manager):
    kwargs = {}
    for key, value in deserialized_kwargs.iteritems():
        kwargs[key] = deserialize_arg_value_to_object(value, model_manager)
    return kwargs


class TaskKwargs(DictRepeater):
    @staticmethod
    def deserialize(fn_get_serialized, model_manager):
        obj = TaskKwargs(fn_get_serialized)
        obj.populate_deserialized(
            deserialize_task_kwargs(fn_get_serialized(), model_manager))
        return obj

    def serialize(self, value):
        return serialize_arg_value_from_object(value)
