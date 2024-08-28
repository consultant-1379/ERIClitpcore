from sqlalchemy import Column
from sqlalchemy import Unicode
from sqlalchemy import Enum
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.ext.declarative import has_inherited_table
from sqlalchemy.orm import relationship, backref, deferred

from litp.data.sa.types import DictAsJSONType


class Plan(object):
    CLASS_NAMES = [
        u"Plan",
        u"SnapshotPlan"
    ]

    UNINITIALISED = u"uninitialised"
    INITIAL = u"initial"
    RUNNING = u"running"
    STOPPING = u"stopping"
    STOPPED = u"stopped"
    FAILED = u"failed"
    SUCCESSFUL = u"successful"
    INVALID = u"invalid"

    STATES = [
        UNINITIALISED, INITIAL, RUNNING, STOPPING, STOPPED, FAILED, SUCCESSFUL,
        INVALID
    ]

    _id = Column("id", Unicode, primary_key=True)
    _class_name = Column("class_name",
        Enum(*CLASS_NAMES,
            name="plan_class_names", convert_unicode=True, native_enum=False),
        nullable=False)
    _state = Column("state",
        Enum(*STATES,
            name="plan_states", convert_unicode=True, native_enum=False),
        nullable=False)
    _plan_type = Column("plan_type", Unicode)
    _snapshot_type = Column("snapshot_type", Unicode)
    _celery_task_id = Column("celery_task_id", Unicode)

    # these do not need to be MutableDicts, they are built and assigned once.
    @declared_attr
    def _required_phases(cls):  # pylint: disable=no-self-argument
        return deferred(
            Column("required_phases", DictAsJSONType), group='phasesort')

    @declared_attr.cascading
    def __tablename__(cls):  # pylint: disable=no-self-argument
        if has_inherited_table(cls):
            return None
        return "plans"

    @declared_attr.cascading
    def __mapper_args__(cls):  # pylint: disable=no-self-argument
        margs = {
            "polymorphic_identity": unicode(
                cls.__name__)  # pylint: disable=no-member
        }
        if not has_inherited_table(cls):
            margs.update({
                "polymorphic_on": cls._class_name,
            })
        return margs

    @declared_attr
    def _plan_tasks(cls):  # pylint: disable=no-self-argument
        return relationship("PlanTask",
            order_by="PlanTask.phase_seq_id, PlanTask.task_seq_id",
            lazy="baked_select",
            cascade="all, delete-orphan",
            passive_deletes=True,
            backref=backref("plan",
                uselist=False,
                lazy="baked_select"
            )
        )
