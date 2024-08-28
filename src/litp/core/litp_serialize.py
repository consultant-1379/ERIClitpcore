##############################################################################
# COPYRIGHT Ericsson AB 2013
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################


import json

from litp.core.litp_logging import LitpLogger

log = LitpLogger()


def json_serializer(obj):
    """
    Convert objects to a dictionary of their representation.

    OPERATION:
    try:
        iterable = iter(obj)
    except TypeError:
        pass
    else:
        return list(iterable)
    return json.JSONEncoder.default(obj)'

    :type  obj: a LITP object.
    :param obj: the object to convert.

    :rtype  obj: Dictionary
    :return obj: Object dictionary.
    """
    result = {}
    class_name = getattr(obj, '__class__', None)
    if class_name:
        result['__class__'] = obj.__class__.__name__
    module_name = getattr(obj, '__module__', None)
    if module_name:
        result['__module__'] = obj.__module__
    if getattr(obj, "__dict__", None):
        result.update(obj.__dict__.items())
    result['parent'] = None
    del result['parent']
    result['logger'] = None
    del result['logger']
    return result


def do_serialize(data):
    """
    Serialize any object to a JSON string

    :type  data: LITP object.
    :param data: The object to be json serialised.

    :rtype:  A json serialised object string.
    :return: Either:
        - A Serialized representation of an object in the default JSON
        format;
        - or, error details.
    """
    try:
        #prevent data already encoded as json to be encoded again
        if not isinstance(data, str):
            return json.dumps(data, default=json_serializer, sort_keys=True,
                              indent=4)
        else:
            return data
    except (TypeError, KeyError, ValueError) as e:
        log.trace.exception(
            'LitpItem.litp_serialize: Failed to serialize data\n%s', data)
        return json.dumps({'error':
                           'litp_serialize: Failed to serialize data',
                            'exception': str(e)})


#FIXME: I have doubts over whether this is actually used..
def serialized(source_function):
    ''' Decorator to automatically
        serialize a function return
        according to litp standart
    '''
    def func_with_serialisation(*args, **kwargs):
        data = source_function(*args, **kwargs)
        return do_serialize(data)
    return func_with_serialisation
