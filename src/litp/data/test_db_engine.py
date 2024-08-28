from sqlalchemy.engine import Engine
from sqlalchemy import engine_from_config
from sqlalchemy import event


@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    # for sqlite3
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def get_engine():
    config = {
        'sqlalchemy.url': 'sqlite://'
    }
    return engine_from_config(config)
