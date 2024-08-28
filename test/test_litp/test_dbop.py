from unittest import TestCase
from mock import MagicMock, patch, Mock

from litp.data.dbop import do_check_model

class TestDBOp(TestCase):

    @patch('litp.data.dbop.scope')
    @patch('litp.data.dbop.DbStorage.create_session')
    @patch('litp.data.dbop.DbStorage.close')
    @patch('litp.data.dbop.DataManager')
    @patch('litp.data.dbop.get_engine')
    @patch('litp.core.nextgen.plugin_manager.PluginManager.add_plugins')
    @patch('litp.core.nextgen.plugin_manager.PluginManager.add_extensions')
    @patch('litp.data.dbop.do_check')
    def test_do_check_model(self, mock_do_check, mock_add_extensions,
                            mock_add_plugins, mock_engine,
                            mock_data_manager, mock_dbstorage_close,
                            mock_dbstorage_create_session,
                            mock_scope):

        do_check_model(MagicMock())
        self.assertTrue(mock_dbstorage_close.called)
        self.assertTrue(mock_engine.called)
        self.assertTrue(mock_dbstorage_create_session.called)
