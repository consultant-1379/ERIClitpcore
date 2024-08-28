##############################################################################
# COPYRIGHT Ericsson AB 2013
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################


from litp.core.litp_logging import LitpLogger

log = LitpLogger()


class EventEmitter(object):

    def __init__(self):
        super(EventEmitter, self).__init__()
        self.handlers = {}

    def emit(self, event_name, *args, **kwargs):
        handlers = self.handlers.get(event_name, [])
        if handlers:
            for handler in handlers:
                if callable(handler):
                    log.trace.debug(
                        "Observable %s: emitting event '%s' to "
                        "handler %s with args: %s, kwargs: %s",
                        self, event_name, handler, args, kwargs)
                    handler(*args, **kwargs)
        else:
            log.trace.debug(
                "Observable %s: emitting event '%s' with no handlers "
                "attached with args: %s, kwargs: %s",
                self, event_name, args, kwargs)

    def attach_handler(self, event_name, handler):
        if callable(handler):
            self.handlers.setdefault(event_name, set()).add(handler)
            log.trace.debug(
                "Observable %s: event '%s' got handler %s attached",
                self, event_name, handler)
        else:
            log.trace.debug(
                "Observable %s: event '%s': non-callable %s was attempted "
                "to be attached", self, event_name, handler)
