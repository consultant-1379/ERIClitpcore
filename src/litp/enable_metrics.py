from litp.metrics import metrics_patch, metrics_logger
from litp.core.task import ConfigTask
from litp.core.task import CleanupTask
from litp.core.task import CallbackTask
from litp.core.task import RemoteExecutionTask
from litp.core.task import OrderedTaskList
import litp.core.constants as constants


def _is_type(obj, qualname):
    '''
    Provides a naive late-binding type evaluation mechanism.
    '''

    obj_qualname = ""
    try:
        obj_qualname += obj.__class__.__module__
        obj_qualname += "."
        obj_qualname += obj.__class__.__name__
    except AttributeError:
        return False
    return obj_qualname == qualname


def extend_metric(metric_logger, name):
    if not hasattr(metric_logger, name):
        extended_metric = metric_logger.extend_with(name)
    else:
        extended_metric = getattr(metric_logger, name)
    return extended_metric


def execution_manager_metrics(obj):
    am = apply_metrics
    if _is_type(obj, 'litp.core.execution_manager.ExecutionManager') or \
        _is_type(obj, 'litp.core.execution_manager.ExecutionManagerNextGen'):

        def get_current_phase():
            try:
                current_phase = int(obj.plan.current_phase)
            except (AttributeError, TypeError):
                return ''
            return str(current_phase + 1)

        am.plan_metric = metrics_logger.extend_with('PLAN')
        am.plan_create_metric = am.plan_metric.extend_with('Create')
        am.model_validation_metric = am.plan_create_metric.extend_with(
            'ModelValidation')
        am.snapshot_model_validation_metric = \
            am.plan_create_metric.extend_with('SnapshotModelValidation')
        am.plugin_create_conf_metric = am.plan_create_metric.extend_with(
            'PluginCreateConfiguration')
        am.plugin_update_model = am.plan_create_metric.extend_with(
            'PluginUpdateModel')
        am.plan_run_metric = am.plan_metric.extend_with('Run')
        am.plan_stop_metric = am.plan_metric.extend_with('Stop')

        am.phase_metric = am.plan_run_metric.extend_with('Phase')
        am.phase_metric.id_handler = get_current_phase

        am.clear_plan_metric = am.plan_run_metric.extend_with('Clear')

        am.disable_puppet_in_phase_metric = am.phase_metric.extend_with(
            'DisablePuppet')

        am.cb_task_metric = am.phase_metric.extend_with('CallbackTask')

        am.serializer_metric = metrics_logger.\
                extend_with('Storage').extend_with('Save')

        def count_model_items_with_state(state):
            item_state_generator = obj.model_manager.data_manager.model.\
                    query_by_states((state,))
            return sum(1 for item in item_state_generator)

        def get_all_nodes():
            return obj.model_manager.query('node') + \
                obj.model_manager.query('ms')

        def get_plan_model_items():
            all_model_items = set()
            for task in obj.plan.get_tasks():
                all_model_items.update(task.all_model_items)
            return all_model_items

        def get_plan_type(plan_type):
            return {
                constants.REMOVE_SNAPSHOT_PLAN: 'RemoveSnapshot',
                constants.CREATE_SNAPSHOT_PLAN: 'CreateSnapshot',
                constants.RESTORE_SNAPSHOT_PLAN: 'RestoreSnapshot',
            }.get(plan_type, 'Deployment')

        def get_plan_status():
            return {
                'stopped': 'Stopped',
                'successful': 'Success',
                'failed': 'Fail',
            }.get(obj.plan_state(), obj.plan_state().capitalize())

        def on_create_plan_args_hook(plan_type, **kwargs):
            if not (hasattr(obj.plan, 'is_initial') and obj.plan.is_initial()):
                return {'Status': 'Aborted'}

            cf_tasks = []
            cb_tasks = []
            re_tasks = []
            cu_tasks = []
            for task in obj.plan.get_tasks():
                if isinstance(task, ConfigTask):
                    cf_tasks.append(task)
                if type(task) == CallbackTask:
                    cb_tasks.append(task)
                if type(task) == RemoteExecutionTask:
                    re_tasks.append(task)
                elif isinstance(task, CleanupTask):
                    cu_tasks.append(task)

            metrics = {
                'Status': 'Created',
                'PlanType': lambda: get_plan_type(plan_type),
                'NoOfPhases': lambda: len(obj.plan.phases),
                'TotalNoOfTasks': lambda: len(obj.plan.get_tasks()),
                'NoOfConfigTasks': lambda: len(cf_tasks),
                'NoOfCallbackTasks': lambda: len(cb_tasks),
                'NoOfRemoteExecutionTasks': lambda: len(re_tasks),
                'NoOfModelItemsInPlan': lambda: len(get_plan_model_items()),
                'NoOfNodes': lambda: len(get_all_nodes()),
                'NoOfItemRemovalTasks': lambda: len(cu_tasks),
                'NoOfClusters': lambda:
                    len(obj.model_manager.query('cluster-base')),
                'NoOfModelItems': lambda:
                    sum(1 for item in obj.model_manager.query_model()),
                'NoOfInitialModelItems': lambda:
                    count_model_items_with_state('Initial'),
                'NoOfUpdatedModelItems': lambda:
                    count_model_items_with_state('Updated'),
                'NoOfAppliedModelItems': lambda:
                    count_model_items_with_state('Applied'),
                'NoOfForRemovalModelItems': lambda:
                    count_model_items_with_state('ForRemoval'),
                'NoOfPlugins': lambda:
                    len(obj.plugin_manager._plugins._by_name.keys()),
                'NoOfExtensions': lambda:
                    len(obj.plugin_manager._extensions._by_name.keys()),
            }
            return metrics

        def on_create_configuration_ret_hook(tasks):
            if not tasks:
                return {}
            metrics = {'TotalNoOfTasks': len(tasks)}
            config_tasks = [task for task in tasks
                            if isinstance(task, ConfigTask)]
            cb_tasks = [task for task in tasks
                        if type(task) == CallbackTask]
            re_tasks = [task for task in tasks
                        if type(task) == RemoteExecutionTask]
            otl_tasks = [task for task in tasks
                        if type(task) == OrderedTaskList]
            if config_tasks:
                metrics['NoOfConfigTasks'] = len(config_tasks)
            if cb_tasks:
                metrics['NoOfCallbackTasks'] = len(cb_tasks)
            if re_tasks:
                metrics['NoOfRemoteExecutionTasks'] = len(re_tasks)
            if otl_tasks:
                metrics['NoOfOrderedTaskList'] = len(otl_tasks)
            return metrics

        def on_run_phase_args_hook(phase_id):
            tasks = obj.plan.get_phase(phase_id)
            metrics = {}
            config_tasks = [task for task in tasks
                            if isinstance(task, ConfigTask)]
            cb_tasks = [task for task in tasks
                        if type(task) == CallbackTask]
            re_tasks = [task for task in tasks
                        if type(task) == RemoteExecutionTask]
            successful_tasks = [task for task in tasks
                        if task.state == constants.TASK_SUCCESS]
            failed_tasks = [task for task in tasks
                        if task.state == constants.TASK_FAILED]
            stopped_tasks = [task for task in tasks
                        if task.state == constants.TASK_STOPPED]
            if config_tasks:
                metrics['NoOfConfigTasks'] = len(config_tasks)
            if cb_tasks:
                metrics['NoOfCallbackTasks'] = len(cb_tasks)
            if re_tasks:
                metrics['NoOfRemoteExecutionTasks'] = len(re_tasks)
            metrics['NoOfSuccessfulTasks'] = len(successful_tasks)
            metrics['NoOfFailedTasks'] = len(failed_tasks)
            metrics['NoOfStoppedTasks'] = len(stopped_tasks)
            return metrics

        def on_process_callback_args_hook(task):
            cb_name = task._callback_name
            try:
                plugins_by_class = obj.plugin_manager._plugins._by_class
                plugin_name = plugins_by_class[task.plugin_class]["name"]
            except KeyError:
                plugin_name = None
            index_in_phase = get_task_index_in_phase(obj.plan, task)
            am.cb_task_metric.id_handler = lambda: \
                '_' + str(index_in_phase) + '_' + str(plugin_name) + \
                '_' + cb_name
            metrics = {'Status': task.state.replace('Failed', 'Fail')}
            return metrics

        def get_task_index_in_phase(plan, task):
            phases = plan.phases
            for phase_tasks in phases:
                for i, phase_task in enumerate(phase_tasks):
                    if phase_task == task:
                        return i
            return -1

        def on_process_callback(task):
            cb_name = task.callback.__name__
            index_in_phase = get_task_index_in_phase(obj.plan, task)
            am.cb_task_metric.id_handler = lambda: \
                '_' + str(index_in_phase) + '_' + cb_name

        metrics_patch(obj, '_create_plan_with_type', am.plan_create_metric,
            args_hook=on_create_plan_args_hook)

        metrics_patch(obj, 'run_plan', am.plan_run_metric,
            Status=get_plan_status,
        )

        # TODO: Sort out metrics in parallel situations
        # TODO: refactor interim solution used to get metrics for spike
        metrics_patch(obj, '_run_phase', am.phase_metric,
            args_hook=on_run_phase_args_hook)
        metrics_patch(obj, '_process_callback_task', am.cb_task_metric,
            args_hook=on_process_callback_args_hook)
        metrics_patch(obj, '_validate_model', am.model_validation_metric)

        metrics_patch(obj, '_clear_plan', am.clear_plan_metric)


def plan_builder(obj):
    am = apply_metrics
    if _is_type(obj, 'litp.core.plan_builder.PlanBuilder'):
        if not hasattr(am, 'plan_metric'):
            am.plan_metric = metrics_logger.extend_with('PLAN')
        if not hasattr(am, 'plan_create_metric'):
            am.plan_create_metric = am.plan_metric.extend_with('Create')
        am.build_metric = am.plan_create_metric.extend_with('Build')
        metrics_patch(obj, 'build', am.build_metric)


def iso_metrics(obj):
    am = apply_metrics
    am.import_metric = metrics_logger.extend_with('ISO').extend_with('Import')

    if _is_type(obj, 'litp.core.iso_import.IsoImporter'):
        am.image_rsync_metric = am.import_metric.extend_with('ImageRsync')
        am.create_repo_metric = am.import_metric.extend_with('CreateRepo')
        am.repo_rsync_metric = am.import_metric.extend_with('RepoRsync')
        am.clean_cache_metric = am.import_metric.extend_with(
            'YumDiscardMetadata')
        am.disable_puppet_metric = am.import_metric.extend_with(
            'DisablePuppet')
        am.run_puppet_on_ms_metric = am.import_metric.extend_with(
            'RunPuppetOnMS')
        am.run_puppet_on_mns_metric = am.import_metric.extend_with(
            'RunPuppetOnMNs')
        am.restart_litp_metric = am.import_metric.extend_with(
            'RestartLITPD')

        def on_rsync_rpms(directory, repo_root):
            am.repo_rsync_metric.id_handler = \
                lambda: '][' + directory.replace(repo_root, '', 1)
            return {}

        def on_create_repo(directory, repo_root):
            am.create_repo_metric.id_handler = \
                lambda: '][' + directory.replace(repo_root, '', 1)
            return {}

        obj.attach_handler('_rsync_rpms', on_rsync_rpms)
        obj.attach_handler('_create_repo', on_create_repo)

        metrics_patch(obj, '_disable_puppet', am.disable_puppet_metric)
        metrics_patch(obj, '_rsync_images', am.image_rsync_metric)
        metrics_patch(obj, '_clean_yum_cache', am.clean_cache_metric)
        metrics_patch(obj, '_rsync_rpms', am.repo_rsync_metric)
        metrics_patch(obj, '_create_repo', am.create_repo_metric)

    if _is_type(obj, 'litp.core.yum_upgrade.YumImport'):
        yum_upgrade_metrics = am.import_metric.extend_with('YumUpgrade')
        metrics_patch(obj, 'import_packages', yum_upgrade_metrics)


def xml_metrics(obj):
    am = apply_metrics

    def count_of_litp_opening_tags(xml_string):
        count = 0
        try:
            count = xml_string.count('<litp:')
        except AttributeError:
            pass
        return count

    def on_xml_export_ret_hook(xml_string):
        metrics = {'NoOfModelItems': count_of_litp_opening_tags(xml_string)}
        return metrics

    def on_xml_import_args_hook(root_vpath, xml_data, *args, **kwargs):
        xml_string = xml_data
        metrics = {'NoOfModelItems': count_of_litp_opening_tags(xml_string)}
        return metrics

    if _is_type(obj, 'litp.xml.xml_exporter.XmlExporter'):
        am.xml_metric = metrics_logger.extend_with('XML').extend_with('Export')
        metrics_patch(obj, 'get_as_xml', am.xml_metric,
            return_value_hook=on_xml_export_ret_hook)

    if _is_type(obj, 'litp.xml.xml_loader.XmlLoader'):
        am.xml_metric = metrics_logger.extend_with('XML').extend_with('Import')
        metrics_patch(obj, 'load', am.xml_metric,
            args_hook=on_xml_import_args_hook)


def plugin_manager_metrics(obj):
    am = apply_metrics
    if _is_type(obj, 'litp.core.plugin_manager.PluginManager') or \
        _is_type(obj, 'litp.core.plugin_manager.PluginManagerNextGen'):

        def on_create_configuration_ret_hook(tasks):
            if not tasks:
                return {}
            metrics = {'TotalNoOfTasks': len(tasks)}
            config_tasks = [task for task in tasks
                            if isinstance(task, ConfigTask)]
            cb_tasks = [task for task in tasks
                        if type(task) == CallbackTask]
            re_tasks = [task for task in tasks
                        if type(task) == RemoteExecutionTask]
            otl_tasks = [task for task in tasks
                        if type(task) == OrderedTaskList]
            if config_tasks:
                metrics['NoOfConfigTasks'] = len(config_tasks)
            if cb_tasks:
                metrics['NoOfCallbackTasks'] = len(cb_tasks)
            if re_tasks:
                metrics['NoOfRemoteExecutionTasks'] = len(re_tasks)
            if otl_tasks:
                metrics['NoOfOrderedTaskList'] = len(otl_tasks)
            return metrics

        def on_plugin_added(name, plugin):
            plugin_validation_metric = extend_metric(
                am.model_validation_metric, name)
            plugin_create_cnf_metric = extend_metric(
                am.plugin_create_conf_metric, name)
            plugin_update_model_metric = extend_metric(
                am.plugin_update_model, name)
            plugin_snapshot_validation = extend_metric(
                am.snapshot_model_validation_metric, name)

            metrics_patch(plugin, 'validate_model', plugin_validation_metric)
            metrics_patch(plugin, 'validate_model_snapshot',
                plugin_snapshot_validation)
            metrics_patch(plugin, 'create_configuration',
                plugin_create_cnf_metric,
                return_value_hook=on_create_configuration_ret_hook)
            metrics_patch(plugin, 'update_model', plugin_update_model_metric)

        obj.attach_handler('plugin_added', on_plugin_added)


def apply_metrics(obj):
    switcher = {
        'litp.core.execution_manager': execution_manager_metrics,
        'litp.core.iso_import': iso_metrics,
        'litp.core.yum_upgrade': iso_metrics,
        'litp.core.plan_builder': plan_builder,
        'litp.core.plugin_manager': plugin_manager_metrics,
        'litp.xml.xml_exporter': xml_metrics,
        'litp.xml.xml_loader': xml_metrics,
    }
    return switcher.get(obj.__module__, lambda _: None)(obj)
