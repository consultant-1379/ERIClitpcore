from litp.core.model_manager import QueryItem
from litp.core.future_property_value import FuturePropertyValue


def serialize_arg_value_from_object(value):
    if isinstance(value, FuturePropertyValue):
        ret = {
            "__class__": type(value).__name__,
            "item": value.query_item.vpath,
            "prop": value.property_name
        }
    elif isinstance(value, set):
        ret = {
            "__class__": type(value).__name__,
            "values": [serialize_arg_value_from_object(obj) for obj in value]
        }
    elif isinstance(value, list):
        ret = [serialize_arg_value_from_object(obj) for obj in value]
    elif isinstance(value, dict):
        ret = dict([
            (obj_key, serialize_arg_value_from_object(obj_value))
            for obj_key, obj_value in value.iteritems()
        ])
    else:
        ret = value
    return ret


def deserialize_arg_value_to_object(value, model_manager):
    if isinstance(value, dict):
        class_name = value.get("__class__")
        if class_name == FuturePropertyValue.__name__:
            item = value.get("item")
            prop = value.get("prop")
            mi = model_manager.get_item(item)
            if mi is None:
                qi = item
            else:
                qi = QueryItem(model_manager, mi)
            ret = FuturePropertyValue(qi, prop)
        elif class_name == set.__name__:
            values = value.get("values", [])
            ret = set([
                deserialize_arg_value_to_object(obj, model_manager)
                for obj in values
            ])
        else:
            ret = dict([
                (obj_key, deserialize_arg_value_to_object(
                    obj_value, model_manager))
                for obj_key, obj_value in value.iteritems()
            ])
    elif isinstance(value, list):
        ret = [
            deserialize_arg_value_to_object(obj, model_manager)
            for obj in value
        ]
    else:
        ret = value
    return ret
