from sqlalchemy import Column
from sqlalchemy import PrimaryKeyConstraint
from sqlalchemy import Index
from sqlalchemy import Unicode
from sqlalchemy import Enum
from sqlalchemy import Boolean
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.ext.declarative import has_inherited_table

from litp.data.sa.types.dict_as_json_type import DictAsJSONType


class ModelItem(object):
    Initial = u"Initial"
    Applied = u"Applied"
    Updated = u"Updated"
    ForRemoval = u"ForRemoval"
    Removed = u"Removed"

    ALL_STATES = [
        Initial,
        Applied,
        Updated,
        ForRemoval,
        Removed
    ]

    CLASS_NAMES = [
        u"ModelItem",
        u"CollectionItem",
        u"RefCollectionItem"
    ]

    _model_id = Column("model_id", Unicode, nullable=False)
    _vpath = Column("vpath", Unicode, nullable=False)

    _class_name = Column("class_name",
        Enum(*CLASS_NAMES,
            name="mi_class_names", convert_unicode=True, native_enum=False),
        nullable=False)
    _item_type_id = Column("item_type_id", Unicode, nullable=False)
    _item_id = Column("item_id", Unicode, nullable=False)
    _parent_vpath = Column("parent_vpath", Unicode)
    _source_vpath = Column("source_vpath", Unicode)

    _properties = Column("properties",
        MutableDict.as_mutable(DictAsJSONType))
    _applied_properties = Column("applied_properties",
        MutableDict.as_mutable(DictAsJSONType))

    _state = Column("state",
        Enum(*ALL_STATES,
            name="mi_states", convert_unicode=True, native_enum=False),
        nullable=False)
    _previous_state = Column("previous_state",
        Enum(*ALL_STATES,
            name="mi_previous_states",
            convert_unicode=True,
            native_enum=False))

    applied_properties_determinable = Column(Boolean(
        name='mi_applied_properties_determinable'), nullable=False)

    @declared_attr.cascading
    def __tablename__(cls):  # pylint: disable=no-self-argument
        if has_inherited_table(cls):
            return None
        return "model"

    @declared_attr.cascading
    def __table_args__(cls):  # pylint: disable=no-self-argument
        if has_inherited_table(cls):
            return None
        args = [
            PrimaryKeyConstraint(cls._model_id, cls._vpath),
            Index("idx_model_id_item_type_id",
                cls._model_id, cls._item_type_id, cls._vpath),
            Index("idx_model_id_parent_vpath",
                cls._model_id, cls._parent_vpath, cls._vpath),
            Index("idx_model_id_source_vpath",
                cls._model_id, cls._source_vpath, cls._vpath),
            Index("idx_model_id_state",
                cls._model_id, cls._state, cls._vpath),
            Index("idx_item_type_id", cls._item_type_id)
        ]
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
