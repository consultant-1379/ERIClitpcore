# pylint: disable=missing-docstring
"""
Database version is random UUID hash.

It is stored in database itself.

It is updated when transaction changing valuable data is committed.
"""

import functools
import uuid

from litp.data.global_options import GlobalOption


SESSION_FLAG = 'mutated'
GLOBAL_ID = 1


def on_before_commit(session):
    """
    Listen to ORM `before_commit` event.
    """
    if version_update_required(session):
        value = {GlobalOption.value: uuid.uuid4().hex}
        session.query(GlobalOption).filter_by(id=GLOBAL_ID).update(value)
        if SESSION_FLAG in session.info:
            del session.info[SESSION_FLAG]


def version_update_required(session):
    """
    Check if db version needs an update.

    Session info can contain flag or session can be dirty.
    """
    if SESSION_FLAG in session.info:
        return True
    return session.new or session.deleted or session.dirty


def set_mutated_flag(session):
    """
    Mark session for on_before_commit
    """
    session.info[SESSION_FLAG] = 1


def ensure_record_exists(session):
    if session.query(GlobalOption).filter_by(id=GLOBAL_ID).count():
        return
    session.add(GlobalOption(id=GLOBAL_ID, value=uuid.uuid4().hex))
    session.commit()


def mark_mutator(method):
    @functools.wraps(method)
    def wrapped(self, *args, **kwargs):
        # pylint: disable=protected-access
        result = method(self, *args, **kwargs)
        set_mutated_flag(self._session)
        return result
    return wrapped
