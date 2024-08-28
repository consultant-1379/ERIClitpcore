import time
import functools


class ETLogger(object):
    def __init__(self, logger_func, prefix):
        self.logger_func = logger_func
        self.prefix = prefix
        self.stack = []

    def _log(self, duration, msg, *args, **kwargs):
        if duration is None:
            ichar = ">"
            duration = "-----"
        else:
            ichar = "<"
            duration = "%.3f" % duration
        indent = ichar * (len(self.stack) + 1)
        log_msg = "[%s] %s [%s] %s" % (self.prefix, indent, duration, msg)
        self.logger_func(log_msg, *args, **kwargs)

    def begin(self, msg, *args, **kwargs):
        self._log(None, msg, *args, **kwargs)
        self.stack.append((
            time.time(),
            msg,
            args,
            kwargs
        ))

    def done(self):
        et = time.time()
        st, msg, args, kwargs = self.stack.pop()
        self._log(et - st, msg, *args, **kwargs)


def et_logged(etlog):
    """ Execute the decorated function and log its elapsed execution time.
    Takes ETLogger instance as argument.

    """
    def decorator(func):
        func_name = func.__name__

        @functools.wraps(func)
        def wrapped(*args, **kwargs):
            etlog.begin(func_name)
            ret = func(*args, **kwargs)
            etlog.done()
            return ret
        return wrapped
    return decorator
