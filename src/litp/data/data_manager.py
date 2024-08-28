from sqlalchemy import bindparam
from sqlalchemy.orm.exc import FlushError

from litp.data.constants import LIVE_MODEL_ID
from litp.data.constants import LAST_SUCCESSFUL_PLAN_MODEL_ID
from litp.data.constants import CURRENT_PLAN_ID
from litp.data.passwd_history import PasswordHistory
from litp.data.types.base import bakery
from litp.data.sa.baked_query_result_wrapper import BakedQueryResultWrapper
from litp.data.db_version import mark_mutator
from litp.data.base_model_data_manager import BaseModelDataManager
from litp.data.model_data_manager import ModelDataManager
from litp.data.model_cache import ModelCache
from litp.core.litp_logging import LitpLogger
from litp.core.etlogger import ETLogger
from litp.core.etlogger import et_logged
from litp.core.model_item import ModelItem
from litp.core.task import Task
from litp.core.plan import BasePlan
from litp.core.plan_task import PlanTask
from litp.core.persisted_task import PersistedTask
from litp.core.extension_info import ExtensionInfo
from litp.core.plugin_info import PluginInfo


log = LitpLogger()
etlog = ETLogger(log.trace.debug, "DataManager")


class DataManagerException(Exception):
    pass


class DataManager(object):
    """
    This class encapsulates the methods of the database session management
    and the non-model specific data manipulation.
    """

    def __init__(self, session):
        self._session = session
        self._model_manager = None
        self._model_id = None
        self.model = None

    def configure(self, model_manager, model_id=LIVE_MODEL_ID):
        """
        Configure DataManager.

        :param model_manager: The ModelManager instance.
        :type  model_manager: :class:`litp.core.model_manager.ModelManager`

        :param model_id: The model id to use.
        :type  model_id: str
        """

        self._model_manager = model_manager
        self._model_id = model_id
        self.configure_model()

    def configure_model(self):
        if self.model:
            self.model.close()
        self.model = ModelDataManager(self, self._model_id)

    def configure_model_cache(self):
        if self.model:
            self.model.close()
        self.model = ModelCache(BaseModelDataManager(self, self._model_id))

    @property
    def session(self):
        """
        Return the session used.
        """

        return self._session

    def close(self):
        """
        Close the database session.
        """

        log.trace.debug("[DataManager] close")

        if self.model:
            self.model.close()

        try:
            if (
                self._session.new or
                self._session.dirty or
                self._session.deleted
            ):
                errmsg_template = (
                    "Pending changes when closing session:\n"
                    "      new: %s\n"
                    "    dirty: %s\n"
                    "  deleted: %s\n"
                )
                errmsg = errmsg_template % (
                    self._session.new,
                    self._session.dirty,
                    self._session.deleted
                )
                log.trace.error(errmsg)
                log.trace.error("Flushing session")
                self._session.flush()
                raise DataManagerException(errmsg)
        finally:
            self._session.close()

    @et_logged(etlog)
    def refresh(self, instance):
        """
        Refresh the instance attributes from database.

        :param instance: The instance to refresh.
        :type  instance: instance of :class:`litp.data.types.base.Base`
        """

        log.trace.debug("[DataManager] refresh")
        self._session.refresh(instance)

    def _get_session_stats(self):
        return (
            len(self._session._new),
            len(self._session.identity_map._modified),
            len(self._session._deleted)
        )

    def _log_identity_keys(self, states):
        for state in states:
            key = self._session.identity_key(instance=state.obj())
            log.trace.error("  - %s", key)

    @et_logged(etlog)
    def commit(self):
        """
        Commit the current database transaction.
        """

        log.trace.debug("[DataManager] commit")

        stats_before_commit = self._get_session_stats()
        try:
            self._session.commit()
        except Exception, e:
            log.trace.error(
                "Exception while committing session", exc_info=True)

            if isinstance(e, FlushError):
                log.trace.error("####################")
                log.trace.error("FlushError detected!")

                stats_after_commit = self._get_session_stats()
                log.trace.error("session stats (new/modified/deleted):")
                log.trace.error("  - before commit: %s", stats_before_commit)
                log.trace.error("  -  after commit: %s", stats_after_commit)

                if self._session._new:
                    log.trace.error("session new:")
                    self._log_identity_keys(self._session._new.iterkeys())

                if self._session.identity_map._modified:
                    log.trace.error("session im modified:")
                    self._log_identity_keys(
                        self._session.identity_map._modified)

                if self._session._deleted:
                    log.trace.error("session deleted:")
                    self._log_identity_keys(self._session._deleted.iterkeys())

                log.trace.error("####################")

            raise e

    @et_logged(etlog)
    def rollback(self):
        """
        Rollback the current database transaction.
        """

        log.trace.debug("[DataManager] rollback")
        self._session.rollback()

    def _initialize_task(self, task):
        task.initialize_from_db(self, self._model_manager)

    def _initialize_plan(self, plan):
        plan.initialize_from_db(self, self._model_manager)

    @mark_mutator
    def add_task(self, task):
        log.trace.debug("[DataManager] add_task: %s", task)
        self._session.add(task)

    @mark_mutator
    def delete_task(self, task):
        log.trace.debug("[DataManager] delete_task: %s", task)
        self._session.delete(task)

    def get_task(self, task_id):
        log.trace.debug("[DataManager] get_task: %s", task_id)
        bquery = bakery(lambda session: session.query(Task))
        task = bquery(self._session).get(task_id)
        if task is None:
            return None
        self._initialize_task(task)
        return task

    def get_task_by_unique_id(self, unique_id):
        log.trace.debug("[DataManager] get_task_by_unique_id: %s", unique_id)
        bquery = bakery(
            lambda session: session
            .query(Task)
            .join(PlanTask)
            .join(BasePlan)
            .filter(
                BasePlan._id == bindparam("plan_id"),
                Task._unique_id == bindparam("unique_id")
            )
        )
        query = bquery(self._session).params(
            plan_id=CURRENT_PLAN_ID,
            unique_id=unique_id
        )
        task = query.first()
        if not task:
            bquery = bakery(
                lambda session: session
                .query(Task)
                .join(PersistedTask)
                .filter(Task._unique_id == bindparam("unique_id"))
            )
            query = bquery(self._session).params(
                unique_id=unique_id
            )
            task = query.first()
        if task:
            self._initialize_task(task)
        return task

    @mark_mutator
    def add_plan(self, plan):
        log.trace.debug("[DataManager] add_plan: %s", plan)
        self._session.add(plan)

    @mark_mutator
    def delete_plan(self, plan):
        log.trace.debug("[DataManager] delete_plan: %s", plan)
        self._session.delete(plan)

    def get_plan(self, plan_id):
        log.trace.debug("[DataManager] get_plan: %s", plan_id)
        bquery = bakery(lambda session: session.query(BasePlan))
        query = bquery(self._session)
        plan = query.get(plan_id)
        if plan is None:
            return None
        self._initialize_plan(plan)
        return plan

    def refresh_plan_phase_tasks(self, plan_id, phase_seq_id):
        log.trace.debug(
            "[DataManager] refresh_plan_phase_tasks: "
            "plan_id=%s, phase_seq_id=%s", plan_id, phase_seq_id)
        for task in self._session.query(Task).join(PlanTask).filter(
            PlanTask.plan_id == plan_id,
            PlanTask.phase_seq_id == phase_seq_id
        ).populate_existing():
            pass

    @mark_mutator
    def add_persisted_task(self, persisted_task):
        log.trace.debug("[DataManager] add_persisted_task: %s", persisted_task)
        self._session.add(persisted_task)

    @mark_mutator
    def update_persisted_tasks(self, hostname, persisted_tasks):
        log.trace.debug(
            "[DataManager] update_persisted_tasks: %s", hostname)
        self._session.query(PersistedTask).filter(
            PersistedTask.hostname == hostname).delete()
        self._session.bulk_save_objects(persisted_tasks)

    def get_persisted_tasks(self):
        log.trace.debug("[DataManager] get_persisted_tasks")
        bquery = bakery(
            lambda session: session
            .query(PersistedTask)
            .order_by(PersistedTask.hostname, PersistedTask.task_seq_id)
        )
        return BakedQueryResultWrapper(bquery(self._session))

    def get_persisted_tasks_for_node(self, hostname):
        log.trace.debug(
            "[DataManager] get_persisted_tasks_for_node: %s", hostname)
        bquery = bakery(
            lambda session: session
            .query(PersistedTask)
            .filter(PersistedTask.hostname == bindparam("hostname"))
            .order_by(PersistedTask.hostname, PersistedTask.task_seq_id)
        )
        return BakedQueryResultWrapper(
            bquery(self._session).params(hostname=hostname))

    @mark_mutator
    def delete_persisted_tasks_for_node(self, hostname):
        log.trace.debug("[DataManager] delete_persisted_tasks: %s", hostname)
        self._session.query(PersistedTask).filter(
            PersistedTask.hostname == hostname).delete()

    def is_task_persisted(self, task):
        log.trace.debug("[DataManager] is_task_persisted")
        bquery = bakery(lambda session: session.query(PersistedTask))
        return bquery(self._session).get(task._id) is not None

    @mark_mutator
    def add_extension(self, extension):
        log.trace.debug("[DataManager] add_extension: %s", extension)
        self._session.add(extension)

    @mark_mutator
    def add_password_history(self, passwd_history):
        bquery = bakery(lambda session: session.query(PasswordHistory))
        if [] == [p for p in bquery(self._session)]:
            self._session.add(passwd_history)

    @mark_mutator
    def delete_extension(self, extension):
        log.trace.debug("[DataManager] delete_extension: %s", extension)
        self._session.delete(extension)

    def get_extensions(self):
        log.trace.debug("[DataManager] get_extensions")
        bquery = bakery(
            lambda session: session
            .query(ExtensionInfo)
            .filter(ExtensionInfo._model_id == bindparam("model_id"))
            .order_by(ExtensionInfo.name)
        )
        return BakedQueryResultWrapper(
            bquery(self._session).params(model_id=LIVE_MODEL_ID))

    @mark_mutator
    def delete_extensions(self):
        log.trace.debug("[DataManager] delete_extensions")
        self._session.query(ExtensionInfo).delete()

    def get_restore_model_extension(self, ext_name):
        log.trace.debug(
            "[DataManager] get_restore_model_extension: %s", ext_name)
        bquery = bakery(lambda session: session.query(ExtensionInfo))
        return bquery(self._session).get(
            (ext_name, LAST_SUCCESSFUL_PLAN_MODEL_ID))

    @mark_mutator
    def add_plugin(self, plugin):
        log.trace.debug("[DataManager] add_plugin: %s", plugin)
        self._session.add(plugin)

    @mark_mutator
    def delete_plugin(self, plugin):
        log.trace.debug("[DataManager] delete_plugin: %s", plugin)
        self._session.delete(plugin)

    def get_plugins(self):
        log.trace.debug("[DataManager] get_plugins")
        bquery = bakery(
            lambda session: session
            .query(PluginInfo)
            .order_by(PluginInfo.name)
        )
        return BakedQueryResultWrapper(bquery(self._session))

    @mark_mutator
    def delete_plugins(self):
        log.trace.debug("[DataManager] delete_plugins")
        self._session.query(PluginInfo).delete()

    def get_model_item_type_ids(self):
        log.trace.debug("[DataManager] get_model_item_type_ids")
        bquery = bakery(
            lambda session: session
            .query(ModelItem._item_type_id)
            .distinct()
        )
        for cols in bquery(self._session):
            yield cols[0]
