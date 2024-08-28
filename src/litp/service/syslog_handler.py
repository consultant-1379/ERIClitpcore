##############################################################################
# COPYRIGHT Ericsson AB 2013
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################


from logging.handlers import SysLogHandler
import socket


class LITPSyslogHandler(SysLogHandler):
    """
    SysLogHandler is extended since it has problems dealing with Rsyslog.
    """

    def __init__(self, *args, **kwargs):
        try:
            SysLogHandler.__init__(self, *args, **kwargs)
                 # we need to catch all exceptions here
        except:  # pylint: disable=W0702
            self.filters = []
            self.lock = False
            self.facility = SysLogHandler.LOG_USER

    def emit(self, record):
        """
        Emit a record.

        The record is formatted, and then sent to the syslog server. If
        exception information is present, it is NOT sent to the server.
        """
        msg = self.format(record) + '\000'
        # We need to convert record level to lowercase, maybe this will
        # change in the future.
        prio = '<%d>' % self.encodePriority(self.facility,
                                            self.mapPriority(record.levelname))

        # The following code prepends a BOM onto the start of the msg.
        # However, rsyslog does not seem to like the BOM.
        # So we comment out these 4 lines.

        # Message is a string. Convert to bytes as required by RFC 5424
        #if type(msg) is unicode:
        #    msg = msg.encode('utf-8')
        #    if codecs:
        #        msg = codecs.BOM_UTF8 + msg
        msg = prio + msg
        try:
            if self.unixsocket:
                try:
                    self.socket.send(msg)
                except socket.error:
                    self._connect_unixsocket(self.address)
                    self.socket.send(msg)
            elif self.socktype == socket.SOCK_DGRAM:  # pylint: disable=E1101
                self.socket.sendto(msg, self.address)
            else:
                self.socket.sendall(msg)
        except (KeyboardInterrupt, SystemExit):
            raise
        except:
            pass
