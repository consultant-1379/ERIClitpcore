from sqlalchemy import Column
from sqlalchemy import Unicode
from sqlalchemy import Integer
from sqlalchemy import ForeignKeyConstraint
from sqlalchemy import Index
from sqlalchemy.orm import relationship
from sqlalchemy.orm import backref
from sqlalchemy.ext.declarative import declared_attr


class PlanTask(object):
    __tablename__ = "plan_tasks"

    task_id = Column("task_id", Unicode, primary_key=True)
    plan_id = Column("plan_id", Unicode, nullable=False)
    phase_seq_id = Column("phase_seq_id", Integer, nullable=False)
    task_seq_id = Column("task_seq_id", Integer, nullable=False)

    @declared_attr
    def __table_args__(cls):  # pylint: disable=no-self-argument
        args = [
            ForeignKeyConstraint(
                ["plan_id"], ["plans.id"],
                onupdate="CASCADE", ondelete="CASCADE"),
            ForeignKeyConstraint(
                ["task_id"], ["tasks.id"], ondelete="CASCADE"),
            Index("idx_plan_task_task_order",
                cls.phase_seq_id, cls.task_seq_id, unique=True)
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
            backref=backref("_plan_task",
                uselist=False,
                lazy="baked_select",
                cascade="all, delete-orphan",
                passive_deletes=True
            )
        )
