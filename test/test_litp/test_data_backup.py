from unittest import TestCase
from mock import patch, MagicMock, Mock
from litp.data.backups import backup
import tarfile
import zlib
from litp.data.backups.constants import (BACKUPS_DB_HASH_PATH)
from litp.data.backups.exceptions import PgDumpException, BinaryException
import subprocess

class TestDataBackup(TestCase):

    @patch('tarfile.open')
    def test_get_backup_version_stamp_errors(self, open_mock):
        for error in [IOError, tarfile.TarError, zlib.error]:
            open_mock.side_effect = error
            self.assertEqual("no-backup-timestamp-available", backup.get_backup_version_stamp("test"))

    @patch('tarfile.open')
    @patch('contextlib.closing')
    @patch('tarfile.TarFile.getnames')
    def test_get_backup_version_stamp_success(self, getnames_mock, closing, open_mock):
        file_mock = MagicMock(spec=tarfile.TarFile)
        open_mock.return_value = file_mock
        closing.return_value = file_mock
        file_mock.getnames.return_value = ['{0}_ssdsdsadssss'.format(BACKUPS_DB_HASH_PATH),
                                      'IUOOUIW343434']
        result = backup.get_backup_version_stamp("test")
        self.assertEqual(result, "DB_HASH_ssdsdsadssss")

    @patch('subprocess.Popen')
    @patch('os.environ.copy')
    @patch('platform.node')
    @patch('litp.data.backups.backup.get_db_credentials')
    def test_dump_litp_db(self, dbcredentials_mock, node_mock, copy_mock, popen_mock):
        dbcredentials_mock.return_value = ('litp', 'litp')
        node_mock.return_value = "ms1"
        copy_mock.return_value = {}
        mock_process = Mock()
        mock_process.communicate.return_value = (
            'Dump successful ', '')
        mock_process.returncode = 0
        popen_mock.return_value = mock_process


        backup.dump_litp_db(MagicMock())
        popen_mock.assert_called_once_with(['/usr/bin/pg_dump', '-Fc', '-c', '-U',
                                            'litp', '-h', 'ms1', 'litp'],
                                            stdout = subprocess.PIPE,
                                            env={'PGSSLMODE': 'verify-full'})

    @patch('subprocess.Popen')
    @patch('os.environ.copy')
    @patch('platform.node')
    @patch('litp.data.backups.backup.get_db_credentials')
    def test_dump_litp_db_pgdump_exception(self, dbcredentials_mock, node_mock, copy_mock, popen_mock):
        dbcredentials_mock.return_value = ('litp', 'litp')
        node_mock.return_value = "ms1"
        copy_mock.return_value = {}
        mock_process = Mock()
        stderr = 'Error Dumping DB'
        mock_process.communicate.return_value = (
            '', stderr)
        mock_process.returncode = 1
        popen_mock.return_value = mock_process

        try:
            backup.dump_litp_db(MagicMock())
        except PgDumpException as e:
            expected_error_msg = ("pgdump failed with returncode {0}.\n"
                                  "STDOUT:\n===\n{1}\n"
                                  "STDERR:\n===\n{2}\n").format(mock_process.returncode, '', stderr)
            self.assertEqual(expected_error_msg, e.message)

        popen_mock.assert_called_once_with(['/usr/bin/pg_dump', '-Fc', '-c', '-U',
                                            'litp', '-h', 'ms1', 'litp'],
                                           stdout=subprocess.PIPE,
                                           env={'PGSSLMODE': 'verify-full'})

    @patch('subprocess.Popen')
    @patch('os.environ.copy')
    @patch('platform.node')
    @patch('litp.data.backups.backup.get_db_credentials')
    def test_dump_litp_db_binary_exception(self, dbcredentials_mock, node_mock, copy_mock, popen_mock):
        dbcredentials_mock.return_value = ('litp', 'litp')
        node_mock.return_value = "ms1"
        copy_mock.return_value = {}
        popen_mock.side_effect = OSError()

        try:
            backup.dump_litp_db(MagicMock())
        except BinaryException as e:
            expected_error_msg = ('Failed to execute binary /usr/bin/pg_dump.')
            self.assertEqual(expected_error_msg, e.message)

        popen_mock.assert_called_once_with(['/usr/bin/pg_dump', '-Fc', '-c', '-U',
                                            'litp', '-h', 'ms1', 'litp'],
                                           stdout=subprocess.PIPE,
                                           env={'PGSSLMODE': 'verify-full'})


    @patch('litp.data.db_storage.DbStorage.close')
    @patch('litp.data.backups.backup.get_engine')
    @patch('litp.data.data_manager.DataManager.close')
    @patch('litp.data.db_storage.DbStorage.create_session')
    def test_get_db_version_stamp(self, dbstorage_mock, datamanagerclose_mock, engine_mock, dbstorageclose_mock):
        dbstorage_mock.return_value.query.return_value.filter_by.return_value.first.return_value = MagicMock(value="123-abc")
        result = backup.get_db_version_stamp(MagicMock())
        self.assertEqual(result, "123-abc")