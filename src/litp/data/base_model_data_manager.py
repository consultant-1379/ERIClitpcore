from sqlalchemy import and_
from sqlalchemy import or_
from sqlalchemy import not_
from sqlalchemy import inspect
from sqlalchemy import bindparam
from sqlalchemy.orm.session import make_transient
from sqlalchemy.orm.util import was_deleted
from sqlalchemy.sql.expression import select
from sqlalchemy.sql.expression import insert
from sqlalchemy.sql.expression import literal

from litp.data.constants import LIVE_MODEL_ID, SNAPSHOT_PLAN_MODEL_ID_PREFIX,\
LAST_SUCCESSFUL_PLAN_MODEL_ID
from litp.data.db_version import mark_mutator
from litp.data.types.base import bakery
from litp.core.model_item import ModelItem
from litp.core.extension_info import ExtensionInfo
from litp.core.litp_logging import LitpLogger


log = LitpLogger()


class BaseModelDataManager(object):
    # pylint: disable=no-member
    """
    This class encapsulates the model specific data manipulation methods.
    """

    def __init__(self, data_manager, model_id):
        self._data_manager = data_manager
        self._model_id = model_id

        log.trace.debug(
            "[BaseModelDataManager] __init__; model_id=%s", model_id)

    @property
    def _session(self):
        return self._data_manager._session

    @property
    def _model_manager(self):
        return self._data_manager._model_manager

    def close(self):
        pass

    def _construct_scope(self, column, exclude):
        scope = []
        for vpath in exclude:
            if vpath.endswith("/"):
                expr = column.startswith(vpath)
            else:
                expr = or_(column == vpath, column.startswith(vpath + "/"))
            scope.append(expr)
        if scope:
            return or_(*scope)

    def _duplicate_extensions(self, from_model_id, to_model_id):
        table = ExtensionInfo.__table__

        model_id_column = table.columns[ExtensionInfo._model_id.name]
        columns = [
            col for col in table.columns.values()
            if col.name != model_id_column.name
        ]

        columns_to_select = [literal(to_model_id)]
        columns_to_select.extend(columns)

        columns_to_insert = [model_id_column]
        columns_to_insert.extend(columns)

        select_clause = select(columns_to_select).where(
                ExtensionInfo._model_id == from_model_id)
        insert_clause = insert(table).from_select(
            columns_to_insert, select_clause)
        self._session.execute(insert_clause)

    def _duplicate_model(self, from_model_id, to_model_id, exclude=None):
        if exclude is None:
            exclude = set()

        table = ModelItem.__table__

        model_id_column = table.columns[ModelItem._model_id.name]
        columns = [
            col for col in table.columns.values()
            if col.name != model_id_column.name
        ]

        columns_to_select = [literal(to_model_id)]
        columns_to_select.extend(columns)

        columns_to_insert = [model_id_column]
        columns_to_insert.extend(columns)

        where_clause = [ModelItem._model_id == from_model_id]
        scope = self._construct_scope(ModelItem._vpath, exclude)
        if scope is not None:
            where_clause.append(not_(scope))
        where_clause = and_(*where_clause)

        select_clause = select(columns_to_select).where(where_clause)
        insert_clause = insert(table).from_select(
            columns_to_insert, select_clause)
        self._session.execute(insert_clause)

    def _delete_backup(self, model_id, exclude=None):
        if exclude is None:
            exclude = set()

        where_clause = [ModelItem._model_id == model_id]
        scope = self._construct_scope(ModelItem._vpath, exclude)
        if scope is not None:
            where_clause.append(not_(scope))
        where_clause = and_(*where_clause)

        self._session.query(ModelItem).filter(where_clause).delete(False)
        self._session.expire_all()

    def delete_snapshot_sets(self, exclude_snapshots):
        """
        Delete all snapshot sets.
        """
        log.trace.debug("[BaseModelDataManager] "
                        "delete_snapshot_sets : ")
        self._delete_snapshot_sets(ExtensionInfo, exclude_snapshots)
        self._delete_snapshot_sets(ModelItem, exclude_snapshots)

    def _delete_snapshot_sets(self, model_table, exclude_snapshots):
        where_clause = [model_table._model_id != LIVE_MODEL_ID]
        where_clause.append(and_(model_table._model_id != \
                                 LAST_SUCCESSFUL_PLAN_MODEL_ID))
        for snapshot_item in exclude_snapshots:
            where_clause.append(and_(
               model_table._model_id != SNAPSHOT_PLAN_MODEL_ID_PREFIX +\
               snapshot_item.item_id))
        where_clause = and_(*where_clause)

        self._session.query(model_table).filter(where_clause).delete(
            synchronize_session="fetch")

    def _delete_extensions(self, model_id):
        self._session.query(ExtensionInfo).filter(
                ExtensionInfo._model_id == model_id).delete()

    def backup_exists(self, model_id):
        """
        Check if the specified model backup exists.

        :param model_id: The id of the model backup.
        :type  model_id: str

        :returns: True if the specified model backup exists, False otherwise
        :rtype: bool
        """

        log.trace.debug("[BaseModelDataManager] backup_exists: %s", model_id)
        bquery = bakery(
            lambda session: session
            .query(ModelItem)
            .filter(ModelItem._model_id == bindparam("model_id"))
        )
        model_item = bquery(self._session).params(model_id=model_id).first()

        bquery = bakery(
            lambda session: session
            .query(ExtensionInfo)
            .filter(ExtensionInfo._model_id == bindparam("model_id"))
        )
        extension_item = bquery(self._session).params(
            model_id=model_id).first()
        return (model_item and extension_item) is not None

    @mark_mutator
    def create_backup(self, model_id):
        """
        Create backup of the live model.

        :param model_id: The id of the model backup to be created.
        :type  model_id: str
        """

        log.trace.debug("[BaseModelDataManager] create_backup: %s", model_id)
        self._delete_backup(model_id)
        self._delete_extensions(model_id)
        self._duplicate_model(LIVE_MODEL_ID, model_id)
        self._duplicate_extensions(LIVE_MODEL_ID, model_id)

    @mark_mutator
    def delete_backup(self, model_id, exclude=None):
        """
        Delete the specified model.

        :param model_id: The id of the model backup to be deleted.
        :type  model_id: str

        :param exclude: Set of vpaths of trees not to delete.
        :type  exclude: set
        """

        log.trace.debug("[BaseModelDataManager] delete_backup: %s", model_id)
        self._delete_backup(model_id, exclude)
        self._delete_extensions(model_id)

    @mark_mutator
    def restore_backup(self, model_id, exclude=None):
        """
        Restore the specified model.

        :param model_id: The id of the model backup to be restored.
        :type  model_id: str

        :param exclude: Set of vpaths of trees not to restore.
        :type  exclude: set
        """

        log.trace.debug("[BaseModelDataManager] restore_backup: %s", model_id)
        self._delete_backup(LIVE_MODEL_ID, exclude=exclude)
        self._duplicate_model(model_id, LIVE_MODEL_ID, exclude=exclude)

    def _initialize_item(self, item):
        item.initialize_from_db(self._model_manager)
        return item

    def exists(self, vpath):
        """
        Check whether the specified model item exists in the model.

        :param vpath: The vpath of the model item.
        :type  vpath: str

        :returns: True if the specified model item exists, False otherwise.
        :rtype: bool
        """

        log.trace.debug("[BaseModelDataManager] exists: %s", vpath)
        return self._get(vpath) is not None

    def get(self, vpath):
        """
        Get the the specified item from the model.

        :param vpath: The vpath of the model item.
        :type  vpath: str

        :returns: The model item with the specified vpath.
        :rtype: :class:`litp.core.model_item.ModelItem` or None if item doesn't
                exists.
        """

        log.trace.debug("[BaseModelDataManager] get: %s", vpath)
        return self._get(vpath)

    def _get(self, vpath):
        bquery = bakery(lambda session: session.query(ModelItem))
        item = bquery(self._session).get((self._model_id, vpath))
        if item is None or item in self._session.deleted:
            return None
        self._initialize_item(item)
        return item

    @mark_mutator
    def add(self, item):
        """
        Add the specified item to the model.

        :param item: The model item to add.
        :type  item: :class:`litp.core.model_item.ModelItem`

        :returns: The added model item.
        :rtype: :class:`litp.core.model_item.ModelItem`
        """

        log.trace.debug("[BaseModelDataManager] add: %s", item.vpath)
        if item not in self._session:
            bquery = bakery(lambda session: session.query(ModelItem))
            existing_item = bquery(self._session).get(
                (item._model_id, item._vpath))
            if existing_item:
                self._session.delete(existing_item)
            else:
                insp = inspect(item)
                if insp.persistent:
                    make_transient(item)

        self._session.add(item)
        return item

    @mark_mutator
    def delete(self, item):
        """
        Delete the specified model item from the model.

        :param item: The model item to delete.
        :type  item: :class:`litp.core.model_item.ModelItem`

        :returns: The deleted model item.
        :rtype: :class:`litp.core.model_item.ModelItem`
        """

        log.trace.debug("[BaseModelDataManager] delete: %s", item.vpath)
        insp = inspect(item)
        if not insp.persistent:
            self._session.expunge(item)
            log.trace.debug("[BaseModelDataManager] delete: "
                "called on non-persistent item %s", item.vpath)
        elif not was_deleted(item):
            self._session.delete(item)
            log.trace.debug("[BaseModelDataManager] delete: "
                "called on deleted item %s", item.vpath)
        return item

    def query_descends(self, parent):
        """
        Get the descendants of the specified model item.

        :param parent: The model item.
        :type  parent: :class:`litp.core.model_item.ModelItem`

        :returns: generator
        """

        log.trace.debug(
            "[BaseModelDataManager] query_descends, parent=%s", parent.vpath)

        bquery = bakery(
            lambda session: session
            .query(ModelItem)
            .filter(ModelItem._model_id == bindparam("model_id"))
        )
        if parent.vpath == "/":
            bquery += lambda q: q.filter(
                ModelItem._parent_vpath.startswith(bindparam("parent_vpath"))
            )
        else:
            bquery += lambda q: q.filter(
                or_(
                    ModelItem._parent_vpath == bindparam("parent_vpath"),
                    ModelItem._parent_vpath.startswith(
                        bindparam("parent_vpath") + "/")
                )
            )
        bquery += lambda q: q.order_by(ModelItem._vpath)

        query = bquery(self._session).params(
            model_id=self._model_id,
            parent_vpath=parent.vpath
        )
        for item in query:
            self._initialize_item(item)
            yield item

    def count_children(self, parent):
        """
        Count the number of children of the specified model item.

        :param parent: The model item.
        :type  item: :class:`litp.core.model_item.ModelItem`

        :returns: Number of children items of the specified model item.
        :rtype: int
        """

        log.trace.debug(
            "[BaseModelDataManager] count_children, parent=%s", parent.vpath)

        return self._session.query(ModelItem._vpath).filter(
            ModelItem._model_id == self._model_id,
            ModelItem._parent_vpath == parent.vpath
        ).count()

    def query_children(self, parent):
        """
        Get the children of the specified model item.

        :param parent: The model item.
        :type  parent: :class:`litp.core.model_item.ModelItem`

        :returns: generator
        """

        log.trace.debug(
            "[BaseModelDataManager] query_children, parent=%s", parent.vpath)

        bquery = bakery(
            lambda session: session
            .query(ModelItem)
            .filter(
                ModelItem._model_id == bindparam("model_id"),
                ModelItem._parent_vpath == bindparam("parent_vpath")
            )
            .order_by(ModelItem._vpath)
        )

        query = bquery(self._session).params(
            model_id=self._model_id,
            parent_vpath=parent.vpath
        )
        for item in query:
            self._initialize_item(item)
            yield item

    def query_inherited(self, source):
        """
        Get the inherited items of the specified model_item.

        :param source: The model item.
        :type  source: :class:`litp.core.model_item.ModelItem`

        :returns: generator
        """

        log.trace.debug(
            "[BaseModelDataManager] query_inherited, source=%s", source.vpath)

        bquery = bakery(
            lambda session: session
            .query(ModelItem)
            .filter(
                ModelItem._model_id == bindparam("model_id"),
                ModelItem._source_vpath == bindparam("source_vpath")
            )
            .order_by(ModelItem._vpath)
        )

        query = bquery(self._session).params(
            model_id=self._model_id,
            source_vpath=source.vpath
        )
        for item in query:
            self._initialize_item(item)
            yield item

    def query_by_item_types(self, item_type_ids):
        """
        Get all items from the model with the specified item types.

        :param item_type_ids: set of item type ids

        :returns: generator
        """

        log.trace.debug(
            "[BaseModelDataManager] query_by_item_types, item_type_ids=%s",
            item_type_ids)

        query = self._session.query(ModelItem).filter(
            ModelItem._model_id == self._model_id,
            ModelItem._item_type_id.in_(item_type_ids)
        ).order_by(ModelItem._vpath)
        for item in query:
            self._initialize_item(item)
            yield item

    def query_by_states(self, states):
        """
        Get all items from the model with the specified states.

        :param states: set of item states

        :returns: generator
        """

        log.trace.debug(
            "[BaseModelDataManager] query_by_states, states=%s", states)

        query = self._session.query(ModelItem).filter(
            ModelItem._model_id == self._model_id,
            ModelItem._state.in_(states)
        ).order_by(ModelItem._vpath)
        for item in query:
            self._initialize_item(item)
            yield item

    def query(self):
        """
        Get all the items from the model.

        :returns: generator
        """

        log.trace.debug("[BaseModelDataManager] query")

        bquery = bakery(
            lambda session: session
            .query(ModelItem)
            .filter(ModelItem._model_id == bindparam("model_id"))
            .order_by(ModelItem._vpath)
        )

        query = bquery(self._session).params(
            model_id=self._model_id
        )
        for item in query:
            self._initialize_item(item)
            yield item
