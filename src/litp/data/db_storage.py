import warnings

from sqlalchemy import engine_from_config, event
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SAWarning
from sqlalchemy.orm import Session

from litp.data.db_version import on_before_commit
from litp.data.types.base import Base
from litp.service.utils import set_db_availability


# change 'ignore' to 'error' to investigate remaining unicode issues
warnings.filterwarnings('ignore',
    r'^Unicode\ type\ received\ non-unicode\ bind\ param\ value', SAWarning)


def get_engine(db_config):
    for item in ['sqlalchemy.url', 'sqlalchemy_pg.url']:
        if db_config.get(item):
            db_config[item] = db_config[item].replace('\'', '')
    return engine_from_config(dict(db_config.items()))


class DbStorage(object):
    def __init__(self, engine):
        self._engine = engine

    def reset(self):
        # in use from tests only, at least at the moment.
        # it's the right thing to drop all and initialize from scratch.
        Base.metadata.drop_all(self._engine)
        Base.metadata.create_all(self._engine)

    def close(self):
        self._engine.dispose()

    def create_session(self):
        session = Session(bind=self._engine, expire_on_commit=False)
        event.listen(session, "before_commit", on_before_commit)
        return session

    @staticmethod
    @event.listens_for(Engine, 'invalidate')
    def connection_invalidated(dbapi_connection, connection_record, exception):
        if exception.__class__.__name__ == 'OperationalError':
            set_db_availability(False)

    @staticmethod
    @event.listens_for(Engine, 'connect')
    def connection_created(dbapi_connection, connection_record):
        set_db_availability(True)
