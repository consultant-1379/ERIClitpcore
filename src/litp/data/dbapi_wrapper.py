# pylint: disable=missing-docstring
import StringIO
import cherrypy
import contextlib

from collections import namedtuple

from alembic.config import Config
from alembic import command

from litp.data.db_storage import get_engine

from litp.data.exceptions import (
    MultipleCurrentsException,
    MultipleHeadsException)

ALEMBIC_CONFIG = '/opt/ericsson/nms/litp/lib/litp/data/alembic.ini'


@contextlib.contextmanager
def dbapi_context(litpd_config):
    cherrypy.config.update(litpd_config)
    # suppress cherrypy's internal logging config for non-service use.
    cherrypy.config.update({'log.screen': False,
                            'log.access_file': '',
                            'log.error_file': ''})
    cherrypy.engine.unsubscribe('graceful', cherrypy.log.reopen_files)
    engine = get_engine(cherrypy.config)
    alembic_cfg = Config(ALEMBIC_CONFIG)
    with engine.begin() as connection:
        alembic_cfg.attributes['connection'] = connection
        # suppress alembic env's internal logging config for automated use.
        alembic_cfg.attributes['init_logging'] = False
        dbapi = DBAPI(alembic_cfg)
        dbapi.ensure_safety()
        attrs = 'dbapi connection cherrypy_config'
        Context = namedtuple('Context', attrs)
        context = Context(dbapi, connection, cherrypy.config)
        yield context


class DBAPI(object):
    def __init__(self, alembic_cfg):
        self.alembic_cfg = alembic_cfg
        self._cache = {}

    def ensure_safety(self):
        if len(self.current()) > 1:
            raise MultipleCurrentsException
        if len(self.heads()) > 1:
            raise MultipleHeadsException

    def current(self):
        return self._do('current')

    def upgrade(self, head):
        return self._do('upgrade', head)

    def stamp(self, head):
        return self._do('stamp', head)

    def heads(self):
        return self._do('heads')

    def _do(self, command_name, *args):
        key = (command_name, tuple(args))
        if key in self._cache:
            return self._cache[key]
        saved_print_stdout = self.alembic_cfg.print_stdout
        try:
            with contextlib.closing(StringIO.StringIO()) as acc:
                self.alembic_cfg.print_stdout = acc.write
                getattr(command, command_name)(self.alembic_cfg, *args)
                result = []
                for line in acc.getvalue().split('\n'):
                    stripped_line = line.strip()
                    if stripped_line:
                        result.append(stripped_line)
                self._cache[key] = result
                return result
        finally:
            self.alembic_cfg.print_stdout = saved_print_stdout
