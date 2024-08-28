from mock import patch, MagicMock
import unittest

from litp.core.litp_logging import LitpLogger
from litp.core.litp_logging import OwnedWatchedFileHandler


class TestLitpLogger(unittest.TestCase):
    def setUp(self):
        self.log = LitpLogger()

    def test_logger(self):
        pass


class TestOwnedWatchedFileHandler(unittest.TestCase):
    def setUp(self):
        self.filename = "/tmp/test.txt"
        self.uid = 100
        self.gid = 100

    @patch('litp.core.litp_logging.os.chown')
    @patch('litp.core.litp_logging.WatchedFileHandler._open')
    def test_open(self, mock_watched_file_handler_open, mock_os_chown):
        mock_watched_file_handler_open.return_value = MagicMock()

        _ = OwnedWatchedFileHandler(self.filename, self.uid, self.gid)
        mock_watched_file_handler_open.assert_called_once()
        mock_os_chown.assert_called_once_with(self.filename, self.uid, self.gid)

    @patch('litp.core.litp_logging.WatchedFileHandler._open')
    @patch('litp.core.litp_logging.log')
    def test_open_IO_Error(self, mock_log, mock_watched_file_handler_open):
        error = "IOError!"
        io_error = IOError(error)
        mock_watched_file_handler_open.side_effect = io_error

        try:
            _ = OwnedWatchedFileHandler(self.filename, self.uid, self.gid)
        except (IOError, OSError) as e:
            self.assertEquals(io_error, e)

        mock_watched_file_handler_open.assert_called_once()
        mock_log.trace.warning.assert_called_once_with(
            "Error opening or changing ownership "
            "of file {0}. {1}".format(self.filename, str(io_error)))

    @patch('litp.core.litp_logging.os.chown')
    @patch('litp.core.litp_logging.WatchedFileHandler._open')
    @patch('litp.core.litp_logging.log')
    def test_open_OSError(self, mock_log, mock_watched_file_handler_open,
                          mock_os_chown):
        error = "OSError!"
        os_error = OSError(error)
        mock_watched_file_handler_open.return_value = MagicMock()
        mock_os_chown.side_effect = os_error

        try:
            _ = OwnedWatchedFileHandler(self.filename, self.uid, self.gid)
        except (IOError, OSError) as e:
            self.assertEquals(os_error, e)

        mock_watched_file_handler_open.assert_called_once()
        mock_os_chown.assert_called_once_with(self.filename, self.uid, self.gid)
        mock_log.trace.warning.assert_called_once_with(
            "Error opening or changing ownership "
            "of file {0}. {1}"
            .format(self.filename, str(os_error)))
