from sqlalchemy import Column
from sqlalchemy import Unicode
from sqlalchemy import Integer
from sqlalchemy import ForeignKeyConstraint
from sqlalchemy import Index
from sqlalchemy.orm import relationship
from sqlalchemy.orm import backref
from sqlalchemy.ext.declarative import declared_attr


class PersistedTask(object):
    __tablename__ = "persisted_tasks"

    task_id = Column("task_id", Unicode, primary_key=True)
    hostname = Column("hostname", Unicode, nullable=False)
    task_seq_id = Column("task_seq_id", Integer, nullable=False)

    @declared_attr
    def __table_args__(cls):  # pylint: disable=no-self-argument
        args = [
            ForeignKeyConstraint(
                ["task_id"], ["tasks.id"], ondelete="CASCADE"),
            Index("idx_persisted_task_hostname_task_seq_id",
                cls.hostname, cls.task_seq_id, unique=True)
        ]
        return tuple(args)

    @declared_attr
    def __mapper_args__(cls):  # pylint: disable=no-self-argument
        return {
            "confirm_deleted_rows": False
        }

    @declared_attr
    def task(cls):  # pylint: disable=no-self-argument
        return relationship("Task",
            uselist=False,
            lazy="joined",
            innerjoin=True,
            backref=backref("_persisted_task",
                uselist=False,
                lazy="baked_select",
                cascade="all, delete-orphan",
                passive_deletes=True
            )
        )
