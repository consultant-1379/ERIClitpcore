import time

from litp.core.litp_logging import LitpLogger
from litp.core.plan import BasePlan
from litp.core.plugin_context_api import PluginApiContext
from litp.core.task import CallbackTask
import litp.core.constants as constants

log = LitpLogger()


class SnapshotExecutionMixin(object):

    def current_snapshot_object(self):
        name = PluginApiContext(self.model_manager).snapshot_name()
        snap_object = self.model_manager.query('snapshot-base', item_id=name)
        if snap_object:
            return snap_object[0]
        return None

    def current_snapshot_status(self):
        # calls snapshot_status on the current snapshot, assuming there is one
        item_id = None
        if self.current_snapshot_object():
            item_id = self.current_snapshot_object().item_id
        return self.snapshot_status(item_id)

    def snapshot_status(self, name):
        snapshot = self.model_manager.query('snapshot-base', item_id=name)
        if not snapshot:
            return 'no_snapshot'
        plan_exists = self.plan_has_tasks()
        # we might have a plan, but it could have a different active snapshot
        # than the one we are checking in this method
        plan_relates_to_name_snapshot = self._plan_related_to_snapshot(name)
        # a snapshot is not failed for restore_snapshot when any of the tasks
        # in plan fails, but it is for create|remove_snapshot
        plan = self.plan
        if plan_exists and not plan.is_active() and\
           self._snapshot_tasks_failure() and\
           getattr(plan, 'snapshot_type', None) != 'restore' and\
           plan_relates_to_name_snapshot:
            return 'failed'
        if snapshot[0].timestamp:
            if ((plan_exists and self.is_snapshot_plan
                 and plan_relates_to_name_snapshot)):
                return 'exists'
            else:
                return 'exists_previous_plan'
        # this is tricky: timestamp being None means the item has been
        # created but the plan was not run yet
        # timestamp being '' means failed snapshot as long as the plan is not
        # running
        if snapshot[0].timestamp is None:
            return 'not_started_yet'
        if plan_exists and plan.is_active():
            return 'in_progress'
        return 'failed'

    def _snapshot_tasks_failure(self):
        # Returns true if any of the snapshot tasks failed.
        if self.is_snapshot_plan:
            return bool(self.plan.find_tasks(state=constants.TASK_FAILED))

    def _process_timestamp_at_ss_phasestart(self, phase_index):
        if not self.is_snapshot_plan:
            return
        if getattr(self.plan, 'snapshot_type', None) != 'restore':
            # set it to failed before starting. Will be set to success
            # if the phase ends without errors.
            # restore_snapshot does not follow that transaction behaviour,
            # see LITPCDS-6525
            self._update_ss_timestamp_failed()

    def _process_timestamp_at_ss_phaseend(self, phase_index, result):
        if not self.is_snapshot_plan:
            return
        if result:
            if getattr(self.plan, 'snapshot_type', None) != 'restore':
                self._update_ss_timestamp_failed()
        else:
            # there has to be a snapshot object, if there isn't we are in quite
            # a bad situation and a AttributeError is the least of our problems
            ss_obj = self.current_snapshot_object()

            # avoid setting it to applied in remove_snapshot
            if not (ss_obj.is_removed() or ss_obj.is_for_removal()):
                self.model_manager.set_snapshot_applied(ss_obj.item_id)
                self._update_ss_timestamp_successful()

    def _update_ss_timestamp_successful(self):
        self._update_ss_timestamp(str(time.time()))

    def _update_ss_timestamp_failed(self):
        self._update_ss_timestamp('')

    def _update_ss_timestamp(self, timestamp):
        log.trace.debug("Updating snapshot timestamp")
        snapshot_object = self.current_snapshot_object()
        if snapshot_object:
            snapshot_item = self.model_manager.get_item(snapshot_object.vpath)
            snapshot_item.set_property('timestamp', timestamp)

    def _create_snapshot_tasks(self, plan_type, config_tasks, cleanup_tasks):
        filtered_snapshot_tasks = []
        # only create snapshot tasks if there is something else to do
        if config_tasks or cleanup_tasks or 'snapshot' in plan_type:
            snapshot_tasks = self._create_plugin_tasks('create_snapshot_plan')
            for task in iter(snapshot_tasks):
                # LITP-11688: drop non-CallbackTask instances.
                # Using type() not isinstance() as RemoteExecutionTask is
                # a subclass of CallbackTask, yet has to be dropped.
                if type(task) is CallbackTask:
                    task.is_snapshot_task = True
                    filtered_snapshot_tasks.append(task)
                else:
                    log.trace.warning(
                        'Removing invalid task {task}: {type} is unsupported '
                        'for snapshot plans. Task returned by plugin '
                        '"{plugin_name}" for "{plan_type}" plan'.format(
                            task=task,
                            type=task.__class__.__name__,
                            plugin_name=getattr(
                                task, 'plugin_name', 'unknown'),
                            plan_type=plan_type))

        return filtered_snapshot_tasks

    def _snapshot_tasks_needed(self, plan_type):
        snapshot_status = self.current_snapshot_status()
        if (plan_type == constants.CREATE_SNAPSHOT_PLAN) and \
           snapshot_status in ('no_snapshot', 'not_started_yet'):
            log.trace.info("No snapshot items found")
            return True
        if plan_type == constants.REMOVE_SNAPSHOT_PLAN and \
                        snapshot_status in \
                        ('exists_previous_plan', 'failed', 'not_started_yet'):
            log.trace.info("Snapshot item found")
            return True
        if ((plan_type == constants.RESTORE_SNAPSHOT_PLAN and
             snapshot_status in ('exists', 'exists_previous_plan'))):
            log.trace.info("Snapshot item to be restored found")
            return True
        if snapshot_status == 'exists_previous_plan':
            log.trace.info("Snapshot item with timestamp exists")
        elif self.snapshot_status(constants.UPGRADE_SNAPSHOT_NAME) == 'failed':
            log.trace.info("Snapshot item with no timestamp, something "
                           "went wrong")
        return False

    def delete_snapshot(self, snapshot_name):
        self.reset_snapshot_active_attribute()
        is_named = snapshot_name != constants.UPGRADE_SNAPSHOT_NAME
        snapshot_item = self.model_manager.get_item(
            self.model_manager.snapshot_path(
                snapshot_name
            )
        )
        if snapshot_item:
            snapshot_item.set_property('active', 'true')
        errors = self._validate_delete_snapshot(snapshot_name, is_named)
        if len(errors) > 0:
            return errors
        self.model_manager.set_snapshot_for_removal(snapshot_name)

        result = self.delete_snapshot_plan()
        if isinstance(result, list):
            errors.extend(result)
            self._delete_post_run_plan_checks(snapshot_name)
            return errors
        elif isinstance(result, BasePlan):
            self.data_manager.commit()
            plan_result = self.run_plan_background()
            # FIXME: plan_result contains thread job info, not a plan result
            if isinstance(plan_result, dict) and plan_result.get('error'):
                errors.extend(plan_result)
                self._delete_post_run_plan_checks(snapshot_name)
            return plan_result
        return errors

    def reset_snapshot_active_attribute(self):
        plan = self.plan
        if plan and plan.is_running():
            return
        for snapshot in self.model_manager.query('snapshot-base'):
            snapshot_item = self.model_manager.get_item(snapshot.vpath)
            snapshot_item.set_property('active', 'false')

    def _validate_delete_snapshot(self, snapshot_name, is_named):
        errors = []
        if ((self.snapshot_status(snapshot_name) not in
             ('not_started_yet', 'exists', 'exists_previous_plan', 'failed'))):
            errors.append({
                "error": constants.DO_NOTHING_PLAN_ERROR,
                "message": self._get_empty_plan_err(
                    constants.REMOVE_SNAPSHOT_PLAN, name=snapshot_name
                )})
        return errors

    def _delete_post_run_plan_checks(self, snapshot_name):
        # something went wrong, the snapshot deletion tasks were not
        # executed or failed during execution. If we leave the item as
        # for removal, any subsequent and successful plan will delete
        # the item, and we don't want that.
        path = self.model_manager.snapshot_path(snapshot_name)
        if self.model_manager.get_item(path):
            self.model_manager.get_item(path).set_previous_state()

    def is_upgrade_snapshot(self, name):
        return name == constants.UPGRADE_SNAPSHOT_NAME
