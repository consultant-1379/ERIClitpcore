##############################################################################
# COPYRIGHT Ericsson AB 2013
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################

"""
Each module has to import LitpLogger and create an instance of the logger.

Usage:
==========
    >>> import logging
    >>> import logging.config
    >>> from litp.core.litp_logging import LitpLogger
    >>>
    >>> logging.config.fileConfig("/etc/litp_logging.conf")
    >>> log = LitpLogger()
    >>>
    >>> def foo():
    >>>     log.event.info("Hello from foo!")
    >>>
    >>> foo()
    2013-10-03 12:53:23,959 - litp.event.__main__ - INFO - Hello from foo!
    >>>

Example calls:
===========
For the trace log:
    >>> log.trace.debug('Foo: %s', foo)
    >>> log.trace.info('Bar: %s Baz: %s', bar, baz)

For event log:
    >>> log.event.info('User did something...')
    >>> log.event.error('Disk on fire!')

Audit log - will most entries here also need to go to event.info? If so, maybe
we can make that happen automatically, within the LitpLogger bject.
    >>> log.audit.info('User updated field %s of item %s to "%s"',
                                           name, vpath, value)

"""

import logging
import os
import threading
from logging.handlers import WatchedFileHandler


class LitpLogger(object):

    """Wrapper for trace, event and audit loggers."""
    def __init__(self):
        self.trace = logging.getLogger('litp.trace')
        self.event = logging.getLogger('litp.event')
        self.audit = logging.getLogger('litp.audit')

    def log_level(self):
        return self.trace.level

    def set_log_name(self, name):
        threading.currentThread().setName(name)

log = LitpLogger()


class OwnedWatchedFileHandler(WatchedFileHandler):
    def __init__(self, file_name, owner_id, group_id):
        self.owner_id = owner_id
        self.group_id = group_id
        WatchedFileHandler.__init__(self, file_name)

    def _open(self):
        try:
            stream = WatchedFileHandler._open(self)
            if stream:
                os.chown(self.baseFilename, self.owner_id, self.group_id)
            return stream
        except (IOError, OSError) as e:
            log.trace.warning("Error opening or changing ownership "
                              "of file {0}. {1}".
                              format(self.baseFilename, str(e)))
            raise e
