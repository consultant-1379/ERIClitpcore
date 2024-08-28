import unittest
from litp.data.db_storage import get_engine
from mock import patch

class DbStorageTestCase(unittest.TestCase):
    @patch('litp.data.db_storage.engine_from_config')
    def test_get_engine(self, mock_engine):
        config = { "sqlalchemy.url": "postgresql+psycopg2://litp@'ms1':'5432'/litp?sslmode=verify-full",
                   "sqlalchemy_pg.url": "postgresql+psycopg2://litp@'ms1':'5432'/postgres?sslmode=verify-full"}

        engine = get_engine(config)
        mock_engine.assert_called_once_with({ "sqlalchemy.url": "postgresql+psycopg2://litp@ms1:5432/litp?sslmode=verify-full",
                                              "sqlalchemy_pg.url": "postgresql+psycopg2://litp@ms1:5432/postgres?sslmode=verify-full"})

