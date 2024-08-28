import unittest
from mock import MagicMock, call, patch
import os
import json
import StringIO
from serializer import litp_serializer


class MockFile(StringIO.StringIO):
    def __init__(self, name):
        StringIO.StringIO.__init__(self) # extending old-style class
        self.permissions = 0666
        self.fileno = lambda: 888
        self.name = name


class TestSerializer(unittest.TestCase):
    def setUp(self):
        self.testBox = litp_serializer.SerializerBox()
        self.serializer = litp_serializer.LitpSerializer("container", "/var", "LKC", 6)
        self.serializer._load_file = self._load_file

    def _load_file(self, filename):
        return open(os.path.join(os.path.abspath(os.path.dirname(__file__)),
            filename)).read()


    @patch("serializer.litp_serializer.os.fsync")
    @patch("serializer.litp_serializer.LitpSerializer._open")
    def test_save_file_permissions(self, mock_open, mock_fsync):
        backup_files = {}

        def _mock_open(filename, mode):
            backup_files[filename] = MockFile(filename)
            return backup_files[filename]
        mock_open.side_effect = _mock_open

        def _mock_fchmod(file_instance, mode):
            backup_files[file_instance.name].permissions = mode

        def _mock_rename(old_name, new_name):
            backup_files[new_name] = backup_files[old_name]
            del backup_files[old_name]

        with patch("serializer.litp_serializer.LitpSerializer._fchmod") as mf:
            with patch("serializer.litp_serializer.os.rename") as mr:
                mf.side_effect = _mock_fchmod
                mr.side_effect = _mock_rename
                self.serializer._save_file('test_filename', 'Hello world!')
                self.assertEqual(backup_files['test_filename'].permissions, 0644)

    def test_create_serializer(self):
        litp_serializer.create_serializer("my hands are just typing words!")

    def test_shutdown_serializer(self):
        litp_serializer.shutdown_serializer()

    def test_start_request(self):
        litp_serializer.start_request("Fiona")

    def test_save_filepath(self):
        self.assertEqual(self.serializer._save_filepath(), "/var/LKC")

    def test_savefile_exists(self):
        self.assertFalse(self.serializer.savefile_exists())

    def test_backup_file_age(self):
        self.assertTrue(self.serializer._backup_file_age() > 0)

    def test_backup_filenames(self):
        self.assertTrue(self.serializer._backup_filename().endswith(".json"))
        self.assertTrue(self.serializer._tmp_filename().endswith(".json"))

    def test_saved_file_requires_backup(self):
        self.serializer.savefile_exists = lambda: True
        mockContainer = MagicMock()
        mockContainer.serialize.return_value = "arf"
        self.serializer.container = mockContainer

        with patch("__builtin__.open") as mockOpen:
            # spec makes the mock object behave like a file object
            mockFile = MagicMock(spec=file)
            # needs to be accessed this way due to the context manager madness in with
            mockFile.__enter__.return_value.read.return_value = "{}"
            mockOpen.return_value = mockFile

            result = self.serializer._saved_file_requires_backup(
                self.serializer._checksum(""))

        self.assertEqual(result, True)


    @patch("json.loads", MagicMock('{LAST_KNOWN_CONFIG_json}'))
    @patch("json.dumps", MagicMock(return_value='{LAST_KNOWN_CONFIG_json}'))
    @patch("serializer.litp_serializer.LitpSerializer._fchmod")
    @patch('serializer.litp_serializer.gmtime', MagicMock(
        return_value=(2015, 1, 5, 15, 55, 5, 0, 5, 0)
    ))
    @patch('serializer.litp_serializer.localtime', MagicMock(
                return_value=(2015, 9, 9, 15, 55, 5, 0, 5, 0)
     ))
    @patch('serializer.litp_serializer.os.fsync', MagicMock(return_value=None))
    @patch('serializer.litp_serializer.shutil.copy')
    @patch('serializer.litp_serializer.os.rename')
    @patch('__builtin__.open')
    @patch('serializer.litp_serializer.LitpSerializer.savefile_exists')
    def test_backup_file_not_opened(self, mock_savefile_exists, mock_open,
            mock_rename, mock_copy, mock_fchmod):
        last_known_config_json = '{LAST_KNOWN_CONFIG_json}'
        last_known_config_cksum = 'a9b5d591a77d4610d61970379b69237d'

        updated_last_known_config_json = '{new_model_json}'
        updated_last_known_config_cksum = '690725e30cc94f0dd628a492db3e6364'

        mock_container = MagicMock()
        mock_container.serialize = MagicMock()
        mock_container.serialize.return_value = '{LAST_KNOWN_CONFIG_json}'
        self.serializer.container = mock_container

        mock_savefile_exists.return_value = False

        # Fresh serializer, there is no backup or LAST_KNOWN_CONFIG yet
        self.assertFalse(self.serializer._saved_file_requires_backup(
            self.serializer._checksum("")))
        self.assertEquals([call()], mock_savefile_exists.mock_calls)
        self.assertEquals([], mock_open.mock_calls)
        mock_savefile_exists.reset_mock()
        mock_open.reset_mock()

        mock_file = MagicMock(spec=file)
        mock_file.__enter__.return_value = MagicMock(
            spec=file,
            read=lambda: last_known_config_json
        )

        mock_open.side_effect = lambda path, mode: mock_file
        # Write the savefile (LAST_KNOWN_CONFIG) for the first time
        self.serializer.save_litp()
        # We write the current model to a temporary file first
        self.assertEquals([call('/var/tmp_20150105155505.json', 'w')], mock_open.mock_calls)
        # Then rename it to LAST_KNOWN_CONFIG
        self.assertEquals([call('/var/tmp_20150105155505.json' ,'/var/LKC')], mock_rename.mock_calls)

        mock_savefile_exists.return_value = True
        mock_savefile_exists.reset_mock()
        mock_open.reset_mock()
        mock_rename.reset_mock()

        # Model serialiasation hasn't changed since LAST_KNOWN_CONFIG
        self.assertFalse(self.serializer._saved_file_requires_backup(
            self.serializer._checksum(last_known_config_json)))

        # LitpSerializer.savefile_exists was called once (and returned True)
        self.assertEquals([call()], mock_savefile_exists.mock_calls)
        # Since LitpSerializer._last_backup_cksum is unset, we hashed
        # LAST_KNOWN_CONFIG
        self.assertEquals([call('/var/LKC', 'rb')], mock_open.mock_calls)
        mock_savefile_exists.reset_mock()
        mock_open.reset_mock()

        self.assertEquals(last_known_config_cksum, self.serializer._last_backup_cksum)

        # The model serialisation has changed since LAST_KNOWN_CONFIG
        self.assertTrue(self.serializer._saved_file_requires_backup(
            self.serializer._checksum(updated_last_known_config_json)))
        self.assertEquals([call()], mock_savefile_exists.mock_calls)
        # We didn't open any file as part of _saved_file_requires_backup()
        # since the checksum was cached
        self.assertEquals([], mock_open.mock_calls)
        mock_savefile_exists.reset_mock()
        mock_open.reset_mock()

        # Test the full save_litp() now
        mock_container.serialize.return_value = updated_last_known_config_json
        self.serializer.save_litp()
        self.assertEquals([call()], mock_savefile_exists.mock_calls)
        # A backup of the model was created
        self.assertEquals([call('/var/LKC', '/var/20150909155505.json')], mock_copy.mock_calls)

        # The current model has changed, so we write it to a temp file
        self.assertEquals([call('/var/tmp_20150105155505.json', 'w')], mock_open.mock_calls)
        # ...then rename it to LAST_KNOWN_CONFIG
        self.assertEquals([call('/var/tmp_20150105155505.json' ,'/var/LKC')], mock_rename.mock_calls)

        # The current checksum has been updated
        self.assertEquals(updated_last_known_config_cksum, self.serializer._last_backup_cksum)

    def test_remove_old_backups(self):
        backup_files = [f for f in [
            '20160226174717.json', '20160226174834.json', '20160226174798.json', '20160226174733.json']]
        with patch('os.listdir', MagicMock(return_value=backup_files)):
            with patch('os.remove', side_effect=lambda x: backup_files.pop(0)):
                self.serializer._remove_old_backups()
                # At max, keep only two backup files
                self.assertEqual(len(backup_files), 2)

    def testLoadPluginsOnly(self):
        lkc_json_data = json.loads(open(os.path.join(os.path.dirname(__file__), "test_last_known_config.json"), "r").read())

        plugins = self.serializer.load_plugins(lkc_json_data)
        self.assertEquals([{"name": "testplugin", "version": "1.1",
            "class": "test_serializer.TestPlugin"}], plugins)

    def testLoadExtensionsOnly(self):
        lkc_json_data = json.loads(open(os.path.join(os.path.dirname(__file__), "test_last_known_config.json"), "r").read())

        plugins = self.serializer.load_extensions(lkc_json_data)
        self.assertEquals([{"name": "testextension", "version": "1.1",
            "class": "test_serializer.TestExtension"}], plugins)
