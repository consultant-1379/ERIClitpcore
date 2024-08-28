from sqlalchemy import Column
from sqlalchemy import Unicode
from sqlalchemy import Boolean
from sqlalchemy import Enum
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.ext.declarative import has_inherited_table
from sqlalchemy.ext.mutable import MutableDict

from litp.data.sa.types import SetAsJSONType
from litp.data.sa.types import SetOfTuplesAsJSONType
from litp.data.sa.types import ListAsJSONType
from litp.data.sa.types import DictAsJSONType
from litp.data.sa.extensions import MutableSet
from litp.data.sa.extensions import MutableList


class Task(object):
    CLASS_NAMES = [
        u"ConfigTask",
        u"CallbackTask",
        u"RemoteExecutionTask",
        u"CleanupTask"
    ]

    STATES = [
        u"Initial",
        u"Running",
        u"Stopped",
        u"Failed",
        u"Success"
    ]

    LOCK_TYPES = [
        u"type_lock",
        u"type_unlock",
        u"type_other"
    ]

    # Task

    _id = Column("id", Unicode, primary_key=True)
    _class_name = Column("class_name",
        Enum(*CLASS_NAMES,
            name="task_class_names", convert_unicode=True, native_enum=False),
        nullable=False)
    _model_item_vpath = Column("item", Unicode, nullable=False)
    description = Column("description", Unicode)
    state = Column("state",
        Enum(*STATES,
            name="task_states", convert_unicode=True, native_enum=False),
        nullable=False)
    _model_items_vpaths = Column("model_items",
        MutableSet.as_mutable(SetAsJSONType))
    _dependencies_serialized = Column("dependencies",
        MutableSet.as_mutable(SetOfTuplesAsJSONType))
    lock_type = Column("lock_type",
        Enum(*LOCK_TYPES,
            name="task_lock_types", convert_unicode=True, native_enum=False),
        nullable=False)
    _locked_node_vpath = Column("locked_node", Unicode)
    group = Column("group", Unicode)
    _args_serialized = Column("args", MutableList.as_mutable(ListAsJSONType))
    _kwargs_serialized = Column(
        "kwargs", MutableDict.as_mutable(DictAsJSONType))

    # ConfigTask
    _unique_id = Column("unique_id", Unicode, index=True)
    _node_vpath = Column("node", Unicode)
    _call_type = Column("call_type", Unicode)
    _call_id = Column("call_id", Unicode)
    _dependency_unique_ids = Column("dep_unique_ids",
        MutableSet.as_mutable(SetAsJSONType))
    _replaces_serialized = Column("replaces",
        MutableSet.as_mutable(SetOfTuplesAsJSONType))
    persist = Column("persist", Boolean(name="task_persist"), nullable=True)

    # CallbackTask
    _plugin_class = Column("plugin_class", Unicode)
    _callback_name = Column("callback_name", Unicode)

    # RemoteExecutionTask
    agent = Column("agent", Unicode)
    action = Column("action", Unicode)
    _nodes_vpaths = Column("nodes",
        MutableSet.as_mutable(SetAsJSONType))

    @declared_attr.cascading
    def __tablename__(cls):  # pylint: disable=no-self-argument
        if has_inherited_table(cls):
            return None
        return "tasks"

    @declared_attr.cascading
    def __table_args__(cls):  # pylint: disable=no-self-argument
        if has_inherited_table(cls):
            return None
        args = []
        return tuple(args)

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
