import cherrypy
import json
import time
import copy

from litp.data.constants import LAST_SUCCESSFUL_PLAN_MODEL_ID
from litp.core import scope
import litp.core.constants as constants
from litp.service.controllers import ItemController, MiscController
from litp.service.decorators import request_method_allowed, \
                                    check_plan_not_running
from litp.core.plan import Plan
from litp.core.validators import ValidationError
from litp.core.litp_logging import LitpLogger
from litp.core.model_item import ModelItem
from litp.migration.migrator import Migrator
from litp.service.utils import update_maintenance
from litp.core.maintenance import set_maintenance_initiator, INITIATED_MANUALLY
from litp.core.iso_import import ISOImport, IsoParser, RepoPathChecker
from litp.core.maintenance import StateFile

log = LitpLogger()


class LitpServiceController(ItemController, MiscController):

    def __init__(self):
        super(LitpServiceController, self).__init__()

    def allows_maintenance_exceptions(self):
        # { handler method: method to decide if maintenance is allowed }
        maint = self.allows_maintenance_method
        return {self.update_service_while_plan_running: maint,
                self.get_service: maint}

    def allows_maintenance_method(self):
        # only the requests sent to /litp/maintenance are allowed to work
        # when litp is in maintenance mode
        return cherrypy.request.path_info == "/litp/{0}".format(
            constants.MAINTENANCE)

    def _get_service(self, service_id):
        messages = []
        if not service_id.startswith('/litp/'):
            service_path = '/litp/' + service_id
        else:
            service_path = service_id
        service_item = self._get_item_from_model_snapshot(service_path)
        item_path = self.normalise_path(service_path)
        if service_item is None:
            messages.append(
                ValidationError(
                    item_path=item_path,
                    error_message='Not found',
                    error_type=constants.INVALID_LOCATION_ERROR
                ).to_dict())

        return messages, service_item

    def _build_error_context(self, service_item_path, messages):
        for message in messages:
            message["type"] = message.pop("error", None)
            uri = message.pop("uri", None)
            if uri is not None:
                message['_links'] = {
                    "self": {"href": self.full_url(uri)}
                }
        context = {
            "_links": {
                "self": {"href": self.full_url(service_item_path)}
            },
            "messages": messages
        }
        return context

    @request_method_allowed(['GET'])
    def list_services(self):
        item = self.model_manager.get_item('/litp')
        if item is not None:
            context = self.generate_hal_context(item, item.children.values())
            context.pop('state')
            embed = context.get('_embedded')
            items = embed.get('item')
            for item in items:
                item.pop('state')
        else:
            return super(LitpServiceController, self).default_route('/litp/')
        return self.render_to_response(context)

    @request_method_allowed(['GET'])
    def get_service(self, service_id, **kwargs):
        messages = []

        service_check_msgs, service_item = self._get_service(service_id)
        messages.extend(service_check_msgs)

        if messages:
            context = self._build_error_context(
                self.normalise_path('/litp/' + service_id),
                messages
            )
        else:
            if service_id == constants.MAINTENANCE:
                self._set_maintenance_props()
            context = self.generate_hal_context(service_item)
            if context.get('state'):
                context.pop('state')
        return self.render_to_response(context)

    def _read_statefile(self):
        # just to ease mocking
        return StateFile.read_state()

    def _get_statefile_value(self):
        file_val = self._read_statefile()
        if StateFile.STATE_UNKNOWN == file_val:
            return StateFile.STATE_FAILED
        elif StateFile.STATE_NONE == file_val:
            if self.model_manager.get_item('/litp/maintenance').\
                    get_property('initiator') is None:
                return StateFile.STATE_NONE
            else:
                return StateFile.STATE_DONE
        return file_val

    def _set_maintenance_props(self):
        maintenance = self.model_manager.get_item(
            "/litp/{0}".format(constants.MAINTENANCE))
        if not maintenance:
            return self.render_to_response(
                self._build_error_context(
                    '/litp',
                    [ValidationError(
                        error_message=('Maintenance item not found'),
                        error_type=constants.INTERNAL_SERVER_ERROR
                    ).to_dict()
                    ]))
        maintenance_state = self._get_statefile_value()
        if maintenance.get_property("status") != maintenance_state:
            maintenance.set_property('status', maintenance_state)

    @check_plan_not_running
    @request_method_allowed(['PUT'])
    def update_service(self, service_id, **kwargs):
        return self.update_service_while_plan_running(
            service_id=service_id, **kwargs)

    def _embed_restore_model_run(self):
        messages, service_item = self._get_service('restore_model')
        if service_item is not None:
            service_properties = {u'update_trigger': u'yes'}
            update_result = self.model_manager.update_item(
                service_item.vpath, **service_properties)
            if not isinstance(update_result, ModelItem):
                messages.extend(
                    [err.to_dict() for err in update_result]
                )
            else:
                action_messages, context, status = self._restore_model(
                    update_result
                )
                messages.extend(action_messages)
        return messages

    @request_method_allowed(['PUT'])
    def update_service_while_plan_running(self, **kwargs):
        messages = []

        service_id = kwargs.pop("service_id", cherrypy.request.path_info)

        service_check_msgs, service_item = self._get_service(service_id)
        messages.extend(service_check_msgs)

        status = None
        if service_item is not None:
            body_data = cherrypy.request.body.fp.read()
            try:
                json_data = json.loads(body_data)
            except ValueError:
                messages.append(
                    ValidationError(
                        item_path=service_item.vpath,
                        error_message=(
                            'Payload is not valid JSON: %s' % body_data
                        ),
                        error_type=constants.INVALID_REQUEST_ERROR
                    ).to_dict())

            cb_service_action = None
            service_name = service_item.item_type.item_type_id
            mandatory_properties = True

            if 'logging' == service_name:
                cb_service_action = self._update_logging
            elif 'prepare-restore' == service_name:
                request_properties = json_data.get("properties", {})
                request_properties["force_remove_snapshot"] = "true" \
                    if request_properties.get("force_remove_snapshot", False) \
                    else "false"
                path = request_properties.get("path", "/")
                if path == "/":
                    error = self._embed_restore_model_run()
                    if error:
                        messages.append(
                            ValidationError(
                                item_path=service_item.vpath,
                                error_message=("Not possible to restore the "
                                    "deployment to a known good state "
                                    "because the last deployment plan "
                                    "was not successfully executed."),
                                error_type=constants.VALIDATION_ERROR
                            ).to_dict())
                cb_service_action = self._update_prepare_restore
                mandatory_properties = False
            elif 'maintenance' == service_name:
                cb_service_action = self._update_maintenance
                messages.extend(self._validate_maintenance_properties(
                    service_item, json_data.get('properties', {})
                ))
            elif 'restore' == service_name:
                cb_service_action = self._restore_model
            elif 'import-iso' == service_name:
                cb_service_action = self._update_import_iso
                mandatory_properties = False
                messages.extend(self._validate_import_iso(
                                    json_data.get('properties', {})))
            else:
                # Some services can't be updated
                messages.append(
                    ValidationError(
                        item_path=service_item.vpath,
                        error_message="This service cannot be updated",
                        error_type=constants.INVALID_REQUEST_ERROR
                    ).to_dict())

            if not messages:
                service_properties = json_data.get('properties', {})
                if service_properties or not mandatory_properties:
                    update_result = self.model_manager.update_item(
                        service_item.vpath, **service_properties)
                    if not isinstance(update_result, ModelItem):
                        messages.extend(
                            [err.to_dict() for err in update_result]
                        )
                    else:
                        updated_service = update_result
                        action_messages, context, status = cb_service_action(
                            updated_service
                        )
                        messages.extend(action_messages)

                else:
                    msg = "Properties must be specified for update"
                    messages.append(
                        ValidationError(
                            item_path=service_item.vpath,
                            error_message=msg,
                            error_type=constants.INVALID_REQUEST_ERROR
                        ).to_dict())

        if messages:
            path = self.normalise_path('/litp/' + service_id)
            if service_item:
                path = self.normalise_path(service_item.vpath)
            context = self._build_error_context(path, messages)
        return self.render_to_response(context, status=status)

    def _restore_model(self, restore_service):
        messages = []
        status = None

        try:
            model_id = LAST_SUCCESSFUL_PLAN_MODEL_ID
            if not self.model_manager.backup_exists(model_id):
                log.event.info(
                    "Could not restore model because no deployment model "
                    "backup is available."
                )
                raise ValueError()

            log.audit.info("Restoring model from backup")
            self.model_manager.restore_backup(model_id)

            litp_root = cherrypy.config.get("litp_root")
            migrator = Migrator(
                litp_root, self.model_manager, self.plugin_manager)
            migrator.apply_migrations(restore_model=True)

            restore_service.set_applied()
            status = constants.OK
        except Exception as restore_ex:  # pylint: disable=W0703
            scope.data_manager.rollback()
            messages.append(
                ValidationError(
                    item_path=restore_service.vpath,
                    error_message="The deployment model couldn't be "
                        "restored",
                    error_type=constants.INTERNAL_SERVER_ERROR
                ).to_dict()
            )
            status = constants.INTERNAL_SERVER

        context = self.generate_hal_context(restore_service)
        return messages, context, status

    def _update_logging(self, logging_service):
        messages = []
        context = None

        force_debug = bool(
            logging_service.properties.get('force_debug') == 'true'
        )
        result = self.model_manager.force_debug(force_debug=force_debug,
                                              normal_start=False)
        if isinstance(result, ValidationError):
            messages.append(result.to_dict())
        else:
            context = self.generate_hal_context(logging_service)

        return messages, context, constants.OK

    def _validate_maintenance_properties(self, item, properties):
        errors = []
        readonly_properties = self.model_manager._get_readonly_properties(
            item, properties)
        for prop in readonly_properties:
            errors.append(ValidationError(
                error_message="Unable to modify readonly "
                "property: %s" % prop,
                item_path=item.vpath,
                property_name=prop,
                error_type=constants.INVALID_REQUEST_ERROR).to_dict())
        return errors

    def _update_maintenance(self, maintenance):
        update_maintenance(maintenance)
        item = set_maintenance_initiator(self.model_manager,
            INITIATED_MANUALLY)
        return [], self.generate_hal_context(item), constants.OK

    @request_method_allowed(['DELETE'])
    def delete_item(self, item_path, **kwargs):
        return self.method_not_allowed(item_path)

    @request_method_allowed(['POST'])
    def create_item(self, item_path, **kwargs):
        return self.method_not_allowed(item_path)

    def _check_updated_properties(self, item):
        updated_props = []

        applied_props = item.applied_properties
        current_props = item.properties

        applied_keys = set(applied_props.keys())
        current_keys = set(current_props.keys())

        new_keys = current_keys - applied_keys

        for p in sorted(applied_keys):
            if current_props.get(p) != applied_props[p]:
                updated_props.append((p, applied_props[p]))

        return {'new': new_keys, 'updated': updated_props}

    def _create_updated_error_message(self, updated_props):

        def join_list(items, prelude, changed_props=True):
            message = ""
            item_count = len(items)
            c = item_count - 1
            for i in items:
                # changed props contain prop name and old value,
                # new ones (that need to be removed) only contain the name
                if changed_props:
                    message += '"%s" to "%s"' % (i[0], i[1])
                else:
                    message += '"%s"' % i
                if c > 1:
                    message += ', '
                elif c == 1:
                    message += ' and '
                c -= 1
            if message:
                message = prelude + ' ' + message
            return message

        messages = []

        if updated_props['new']:
            messages.append(join_list(updated_props['new'],
                                      "remove additional properties:", False))

        if updated_props['updated']:
            messages.append(join_list(updated_props['updated'],
                                      "revert updated properties:"))

        error_message = '; '.join(messages)

        if error_message:
            error_message += ' and rerun prepare_restore'
            error_message = error_message[0].upper() + error_message[1:]

        return error_message

    def _update_prepare_restore(self, prepare_restore_service):
        actions = prepare_restore_service.properties.get('actions')
        path = prepare_restore_service.properties.get('path')
        force_remove_snapshot = prepare_restore_service.properties.get(
                                                    'force_remove_snapshot')

        log.trace.info('Called prepare_restore with actions=%s path=%s',
                       actions, path)

        messages = []
        context = None
        exclude_paths = copy.copy(constants.PrepareRestoreData.EXCLUDE_PATHS)

        item = self.model_manager.get_item(path)
        if not item:
            messages.extend([
                ValidationError(
                    error_message="Item not found '%s'" % path,
                    property_name="path",
                    item_path=prepare_restore_service.vpath
                ).to_dict()
            ])
            return messages, context, constants.UNPROCESSABLE

        if path != "/" and (not item.is_node() or item.is_ms()):
            messages.extend([
                ValidationError(
                    error_message="Item is not a node '%s'" % path,
                    property_name="path",
                    item_path=prepare_restore_service.vpath
                ).to_dict()
            ])
            return messages, context, constants.UNPROCESSABLE

        if path != "/":
            prepare_restore_service.properties["path"] = "/"
            cluster = self.model_manager.get_cluster(item)

            if cluster:
                exclude_nodes = set()
                exclude_clusters = set()

                for other_node in self.model_manager.get_all_nodes():
                    if other_node.is_ms() or other_node.vpath == item.vpath:
                        continue

                    other_cluster = self.model_manager.get_cluster(other_node)
                    if other_cluster.vpath == cluster.vpath:
                        exclude_nodes.add(other_node.vpath)
                    else:
                        exclude_clusters.add(other_cluster.vpath)

                for (name, ex_set) in [('clusters', exclude_clusters),
                                       ('nodes', exclude_nodes)]:
                    if ex_set:
                        log.trace.debug("prepare_restore exclude %s: %s" %
                                        (name, ex_set))
                        exclude_paths.extend(ex_set)

                exclude_paths.extend([cluster.vpath + child_path
                   for child_path in ('/fencing_disks/', '/storage_profile/')])

                for cs in cluster.services:
                    exclude_paths.append(cs.vpath + '/filesystems/')

        results = self._execute_prepare_restore_actions(
            actions, "/", exclude_paths, force_remove_snapshot)

        log.trace.info(
            'Finished prepare_restore with actions=%s path=%s results=%s',
            actions, path, results)

        if isinstance(results, list):
            messages.extend(results)
            return messages, context, constants.UNPROCESSABLE
        else:
            context = self.generate_hal_context(prepare_restore_service)
        return messages, context, constants.OK

    def _execute_prepare_restore_actions(self, actions, path, exclude_paths,
                                         force_remove_snapshot):
        if 'all' in actions:
            actions = constants.PREPARE_FOR_RESTORE_ACTIONS

        if 'set_to_initial' in actions:
            locked_node = self.model_manager._node_left_locked()
            if locked_node is not None:
                self.model_manager._update_item(
                    locked_node.vpath,
                    {'is_locked': 'false'},
                    validate_readonly=False
                )

            results = self._set_items_to_initial_from(path, exclude_paths)

        if not results and 'remove_upgrade' in actions:
            self._remove_upgrade()

        if not results and 'remove_snapshot' in actions:
            results = self._remove_snapshot(force_remove_snapshot)

        if not results and 'remove_last_plan' in actions:
            self._remove_last_plan()

        if not results and 'remove_certs' in actions:
            results = self._remove_certs(path)

        if not results:
            self._purge_node_tasks()

        if not results and 'remove_manifests' in actions:
            results = self._remove_manifests()

        return results

    def _remove_manifests(self):
        self.puppet_manager.remove_manifests_clean_tasks()

    def _set_items_to_initial_from(self, path, exclude_paths):
        return self.model_manager.set_items_to_initial_from(
            path, exclude_paths)

    def _remove_upgrade(self):
        upgrades = self.model_manager.query('upgrade')
        for upgrade in upgrades:
            self.model_manager.remove_item(upgrade.get_vpath())

    def _remove_snapshot(self, force_remove_snapshot):
        snapshots = self.model_manager.query('snapshot-base')
        for snapshot in snapshots:
            snapshot_name = snapshot.item_id
            snapshot.set_property('force', force_remove_snapshot)
            result = self.execution_manager.delete_snapshot(snapshot_name)
            self.execution_manager.forget_cached_plan()
            while (not isinstance(result, list) and
                    self.execution_manager.plan_state() not in [
                        Plan.FAILED, Plan.STOPPED]):
                if (self.execution_manager.plan_state() == Plan.SUCCESSFUL
                        and not self.model_manager.query('snapshot-base',
                            item_id=snapshot_name)):
                    time.sleep(2)
                    break
                time.sleep(2)
                self.execution_manager.forget_cached_plan()

            if self.execution_manager.plan_state() == Plan.FAILED:
                result = [ValidationError(
                            item_path=snapshot.get_vpath(),
                            error_type=constants.INTERNAL_SERVER_ERROR,
                            error_message='Remove snapshot plan failed'
                            ).to_dict()]

            if isinstance(result, list):
                return result

    def _remove_last_plan(self):
        self.execution_manager.delete_plan()

    def _remove_certs(self, path):
        self.puppet_manager.remove_certs()

    def _purge_node_tasks(self):
        self.puppet_manager.purge_node_tasks()

    def _validate_import_iso(self, import_iso_service):
        messages = []
        parser = IsoParser(import_iso_service.get('source_path'),
                           RepoPathChecker(self.model_manager))
        import_iso_items = self.model_manager.query('import-iso')
        errors = parser.validate()
        for iiso in import_iso_items:
            if errors:
                log.trace.error('Failure: %s' % errors)
                messages += [ValidationError(
                        error_message=error,
                        item_path=iiso.vpath).to_dict()
                        for error in errors]
        return messages

    def _update_import_iso(self, import_iso_service):
        messages = []
        context = None

        importer = ISOImport(
            import_iso_service.properties.get('source_path'),
            self.model_manager
        )

        errors = importer.run_import()

        if errors:
            for err in errors:
                if isinstance(err, ValidationError):
                    messages.append(err.to_dict())

        if len(messages) > 0:
            return messages, context, constants.UNPROCESSABLE
        else:
            context = self.generate_hal_context(import_iso_service)
        return messages, context, constants.OK
