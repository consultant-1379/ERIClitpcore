import unittest
import logging
import socket
import mock
from logging.handlers import SysLogHandler
from litp.service.syslog_handler import LITPSyslogHandler


class SyslogHandlerTest(unittest.TestCase):
    """
    LITPSyslogHandler is a reduced version of method 'emit' in SysLogHandler.
    Functionality belongs to the standard library logging so we test
    that the exceptions are in place
    """
    @mock.patch.object(SysLogHandler, '__init__')
    def test_syslog_handler_basics(self, mocked_init):
        SysLogHandler.__init__.side_effect = SystemExit
        hdlr = LITPSyslogHandler()
        self.assertTrue((hdlr.filters == [] and
                         hdlr.lock == False and
                         hdlr.facility == SysLogHandler.LOG_USER))

    def test_syslog_handler_1(self):
        hdlr = LITPSyslogHandler()
        hdlr.unixsocket = True
        hdlr.socket = mock.MagicMock()
        hdlr.emit(mock.MagicMock())
        self.assertTrue(hdlr.socket.send.called)

    class mock_except(object):
        '''
        As date Jan/2014 jenkin's mock version is 0.8.0 that does not like
        iters in side_effect arg. Thus this little class is needed
        '''
        def __init__(self):
            self.called = 0

        def __call__(self, msg):
            if self.called == 0:
                raise socket.error
                self.called += 1
            else:
                return 'OK'

    def test_syslog_handler_connect_unix(self):
        hdlr = LITPSyslogHandler()
        hdlr.unixsocket = True
        hdlr.socket = mock.MagicMock()
        hdlr._connect_unixsocket = mock.MagicMock()
        hdlr.socket.send = mock.MagicMock()
        hdlr.socket.send.side_effect = self.mock_except()
        hdlr.emit(mock.MagicMock())
        self.assertTrue(hdlr.socket.send.called)
        self.assertTrue(hdlr.socket.send.call_count == 2)

    def test_syslog_handler_socktype(self):
        hdlr = LITPSyslogHandler()
        hdlr.unixsocket = False
        hdlr.socktype = socket.SOCK_DGRAM
        hdlr.socket = mock.MagicMock()
        hdlr.emit(mock.MagicMock())
        self.assertTrue(hdlr.socket.sendto.called)

    def test_syslog_handler_sendall(self):
        hdlr = LITPSyslogHandler()
        hdlr.unixsocket = False
        hdlr.socktype = False
        hdlr.socket = mock.MagicMock()
        hdlr.emit(mock.MagicMock())
        self.assertTrue(hdlr.socket.sendall.called)

    def test_syslog_handler_except1(self):
        hdlr = LITPSyslogHandler()
        hdlr.unixsocket = False
        hdlr.socktype = False
        hdlr.socket = mock.MagicMock()
        hdlr.socket.sendall = mock.MagicMock()

        hdlr.socket.sendall.side_effect = KeyboardInterrupt
        self.assertRaises(KeyboardInterrupt, hdlr.emit, mock.MagicMock())

        hdlr.socket.sendall.side_effect = SystemExit
        self.assertRaises(SystemExit, hdlr.emit, mock.MagicMock())

    def test_syslog_handlert_except_e(self):
        hdlr = LITPSyslogHandler()
        hdlr.unixsocket = True
        hdlr.socktype = False
        hdlr._connect_unixsocket = mock.MagicMock()
        hdlr.socket = mock.MagicMock()
        hdlr.socket.sendall = mock.MagicMock()
        hdlr.socket.sendall.side_effect = ValueError
        self.assertTrue(hdlr.emit(mock.MagicMock()) is None)

if __name__ == '__main__':
    unittest.main()
