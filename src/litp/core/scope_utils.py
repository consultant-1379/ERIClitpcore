from contextlib import contextmanager
from functools import wraps

import cherrypy

from litp.core import scope
from litp.data.data_manager import DataManager


def setup_threadlocal_scope():
    if hasattr(scope, "data_manager"):
        raise Exception("scope already initialized?")

    db_storage = cherrypy.config["db_storage"]
    model_manager = cherrypy.config["model_manager"]

    session = db_storage.create_session()
    data_manager = DataManager(session)
    data_manager.configure(model_manager)

    scope.data_manager = data_manager


def cleanup_threadlocal_scope():
    try:
        if scope.data_manager._session.is_active:
            try:
                scope.data_manager.commit()
            except Exception:  # pylint: disable=broad-except
                scope.data_manager.rollback()
                raise
        else:
            scope.data_manager.rollback()
    finally:
        try:
            scope.data_manager.close()
        except Exception:  # pylint: disable=broad-except
            pass

        for attr_name in scope.__dict__.keys():
            delattr(scope, attr_name)


@contextmanager
def threadlocal_scope_context():
    setup_threadlocal_scope()
    try:
        yield
    finally:
        cleanup_threadlocal_scope()


def threadlocal_scope(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        with threadlocal_scope_context():
            return fn(*args, **kwargs)
    return wrapper
