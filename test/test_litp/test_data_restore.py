from unittest import TestCase
from mock import patch, MagicMock, Mock
from litp.data.backups.restore import restore_litp_db
from litp.data.backups.exceptions import PgRestoreException
import tarfile
import subprocess


class TestDataRestore(TestCase):

    @patch('tarfile.TarFile.extractfile')
    @patch('subprocess.Popen')
    @patch('platform.node')
    @patch('litp.data.backups.restore.closing')
    def test_restore_litp_db(self, mock_closing, mock_node, mock_popen, mock_extractfile):
        file_mock = MagicMock(spec=tarfile.TarFile)
        mock_closing.return_value = file_mock
        mock_extractfile = file_mock

        mock_node.return_value = "ms1"
        mock_process = Mock()
        mock_process.communicate.return_value = (
            'Restore successful ', '')
        mock_process.returncode = 0
        mock_popen.return_value = mock_process
        tarball = MagicMock()
        dump = MagicMock()

        restore_litp_db(tarball, dump, "litp")

        mock_popen.assert_called_once_with("su - postgres -c 'PGSSLMODE=verify-full /usr/bin/pg_restore -h ms1 -d litp -c'",
                                           shell=True,
                                           stdout=subprocess.PIPE,
                                           stdin=subprocess.PIPE)

    @patch('tarfile.TarFile.extractfile')
    @patch('subprocess.Popen')
    @patch('platform.node')
    @patch('litp.data.backups.restore.closing')
    def test_restore_litp_db_pg_restore_exception(self, mock_closing, mock_node, mock_popen, mock_extractfile):
        file_mock = MagicMock(spec=tarfile.TarFile)
        mock_closing.return_value = file_mock
        mock_extractfile = file_mock

        mock_node.return_value = "ms1"
        mock_process = Mock()
        stderr = 'Restore Failed'
        mock_process.communicate.return_value = (
            '', stderr)
        mock_process.returncode = 1
        mock_popen.return_value = mock_process
        tarball = MagicMock()
        dump = MagicMock()

        try:
            restore_litp_db(tarball, dump, "litp")
        except PgRestoreException as e:
            expected_error_msg = ("pgrestore failed with returncode {0}.\n"
                                  "STDOUT:\n===\n{1}\n"
                                  "STDERR:\n===\n{2}\n").format(mock_process.returncode, '', stderr)
            self.assertEqual(expected_error_msg, e.message)

        mock_popen.assert_called_once_with(
            "su - postgres -c 'PGSSLMODE=verify-full /usr/bin/pg_restore -h ms1 -d litp -c'",
            shell=True,
            stdout=subprocess.PIPE,
            stdin=subprocess.PIPE)
