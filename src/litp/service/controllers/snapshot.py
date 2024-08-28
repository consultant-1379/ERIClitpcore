import cherrypy
import json
import re

from litp.data.constants import LAST_SUCCESSFUL_PLAN_MODEL_ID
from litp.core import constants
from litp.core.litp_logging import LitpLogger
from litp.core.plan import BasePlan
from litp.core.validators import ValidationError
from litp.service import utils
from litp.service.controllers.baseplan import BasePlanController
from litp.service.decorators import (request_method_allowed,
                                     check_plan_not_running,
                                     check_cannot_create_plan)
from litp.core.model_item import ModelItem
from litp.core.model_manager import QueryItem


log = LitpLogger()


CREATE_SNAPSHOT = 'Create snapshot'
REMOVE_SNAPSHOT = 'Remove snapshot'
RESTORE_SNAPSHOT = 'Restore snapshot'


class SnapshotController(BasePlanController):

    def __init__(self):
        super(SnapshotController, self).__init__()
        self.snapshot_dir = cherrypy.config.get('dbase_root')

    def _validate_force_properties(self, json_data):
        validation_errors = []
        item_properties = json_data.get('properties', {})
        if item_properties:
            state = item_properties.get("force")
            pattern = re.compile(r'^([tT]rue|[fF]alse)$')
            error_message = ""
            if state is not None and pattern.search(str(state)) == None:
                error_message = (
                    "Invalid value for force specified: '%s'" % state)
            if state is None:
                error_message = "Property 'force' must be specified"
            if error_message is not "":
                validation_errors.append(
                                    ValidationError(
                        item_path=constants.UPGRADE_SNAPSHOT_PATH,
                        error_message=error_message,
                        error_type=constants.INVALID_REQUEST_ERROR).to_dict()
                )
        else:
            msg = "Properties must be specified for update"
            validation_errors.append(
                ValidationError(
                    item_path=constants.UPGRADE_SNAPSHOT_PATH,
                    error_message=msg,
                    error_type=constants.INVALID_REQUEST_ERROR
                ).to_dict())
        return validation_errors

    def _exclude_nodes_re(self):
        property_types = self.model_manager.property_types
        hostname_re = property_types['hostname'].regex.strip('^$')
        exclude_nodes_re = (r"^"
                r"("
                + hostname_re +
                r",)*"
                + hostname_re +
                r"$")
        return exclude_nodes_re

    def _validate_exclude_nodes(self, snapshot_name, exclude_nodes):
        def _validation_error(message):
            return ValidationError(
                item_path="{0}/{1}".format(
                    constants.SNAPSHOT_BASE_PATH, snapshot_name),
                error_message=message,
                error_type=constants.INVALID_REQUEST_ERROR
            ).to_dict()
        exclude_nodes_re = self._exclude_nodes_re()

        messages = []
        exclude_nodes_list = exclude_nodes.split(',')
        nodes = set(self.model_manager.get_all_nodes())
        extant_hostnames = set(node_mi.hostname for node_mi in nodes)
        # set(['']) is for cases like exclude_nodes = ',node'
        nonexistent_hostnames = [hostname for hostname in exclude_nodes_list \
                if hostname not in extant_hostnames | set([''])]
        existent_nodes = [node_mi for node_mi in nodes \
                if node_mi.hostname in exclude_nodes_list]
        seen = set()
        duplicates = [hostname for hostname in exclude_nodes_list \
                if hostname in seen or seen.add(hostname)]

        # Restrict to named snapshots only
        if snapshot_name == constants.UPGRADE_SNAPSHOT_NAME:
            message = "Use exclude_nodes with named snapshot only"
            messages.append(_validation_error(message))

        # Empty exclude_nodes
        if exclude_nodes == '':
            message = 'exclude_nodes cannot be an empty string'
            messages.append(_validation_error(message))

        # Validate the comma-separated list
        elif not re.match(exclude_nodes_re, exclude_nodes):
            message = "exclude_nodes malformed"
            messages.append(_validation_error(message))

        # All nodes exist in the model
        elif nonexistent_hostnames:
            message = 'Nonexistent hostnames in exclude_nodes: {0}'.format(
                ','.join(nonexistent_hostnames))
            messages.append(_validation_error(message))

        # Exclude ms
        if any(node_mi.is_ms() for node_mi in existent_nodes):
            message = 'exclude_nodes cannot contain MS'
            messages.append(_validation_error(message))

        # Check for duplicates
        if duplicates:
            message = 'exclude_nodes contains duplicate entries: {0}'.format(
                ','.join(duplicates))
            messages.append(_validation_error(message))

        return messages

    def _exclude_nodes_query_items(self, exclude_nodes):
        if exclude_nodes is None:
            return set()
        exclude_nodes_query_items = set()
        exclude_nodes_hostnames = set(exclude_nodes.split(','))
        all_nodes = self.model_manager.get_all_nodes()
        for node_mi in all_nodes:
            if node_mi.hostname in exclude_nodes_hostnames:
                exclude_nodes_query_items.add(
                        QueryItem(self.model_manager, node_mi))
        return exclude_nodes_query_items

    @check_cannot_create_plan
    @check_plan_not_running
    @request_method_allowed(['POST'])
    def create_snapshot(self,
                        snapshot_name=constants.UPGRADE_SNAPSHOT_NAME,
                        *args,
                        **kwargs):
        """
        0- reset active attribute
        1- deserialize request body
        2- validate snapshot name
        3- validate exclude_nodes
        4- create snapshot item
        5- create plan
        6- run plan
        If any of those steps fail, return errors without executing the rest
        """
        self.execution_manager.reset_snapshot_active_attribute()
        status, messages = None, []
        body = self._get_request_body(
                                    cherrypy.request.body.fp.read(), messages)
        url = '/snapshots/%s' % snapshot_name
        if messages:
            # invalid request body
            context = self._get_context_from_messages(messages)
            return self.render_to_response(context, status=status)

        exclude_nodes = kwargs.get('exclude_nodes', None)
        if exclude_nodes is not None:
            messages.extend(
                    self._validate_exclude_nodes(snapshot_name, exclude_nodes))
        if messages:
            context = self._parse_messages(messages, url)
            self.get_status_from_messages(messages, status)
            return self.render_to_response(context, status=status)

        if body.get('type') is not None:
            rest_error = self._validate_and_create_snapshot_item(
                snapshot_name, body.get('type'))
            if rest_error:
                return rest_error
        else:
            messages.append(ValidationError(
                error_type=constants.INVALID_REQUEST_ERROR,
                error_message="item-type not specified in request body",
                item_path='/snapshots/%s' % snapshot_name
                ).to_dict()
            )

        if messages:
            context = self._parse_messages(messages, url)
            self.get_status_from_messages(messages, status)
            return self.render_to_response(context, status=status)

        exclude_nodes_qi = self._exclude_nodes_query_items(exclude_nodes)
        with utils.set_exclude_nodes(self.execution_manager, exclude_nodes_qi):
            messages, status, context = self._create_plan_and_return_errors(
                self.execution_manager.create_snapshot_plan,
                'create')
        if messages:
            # remove the snapshot item we just created, create_plan failed
            self.model_manager.remove_snapshot_item(snapshot_name)
            context = self._get_context_from_messages(
                messages, path=self.model_manager.snapshot_path(snapshot_name)
            )
            return self.render_to_response(context, status=status)

        messages, status = self._run_plan_and_return_errors(status)
        if messages:
            context = self._get_context_from_messages(messages)
        return self.render_to_response(context, status=status)

    @check_cannot_create_plan
    @check_plan_not_running
    @request_method_allowed(['PUT'])
    def restore_or_remove_snapshot(self, snapshot_name, *args, **kwargs):
        """
          Proxy for REST PUT requests. It calls to _restore_snapshot or
          _delete_snapshot depending on the value of 'action' argument.
        """

        errors = []
        messages = []
        json_data = self._get_request_body(cherrypy.request.body.fp.read(),
                                           errors)

        if errors:
            context = self._parse_messages(
                                      errors, constants.UPGRADE_SNAPSHOT_PATH
                                           )
            return self.render_to_response(context, status=None)

        if json_data:
            messages.extend(self._validate_force_properties(json_data))

        if messages:
            context = self._parse_messages(messages,
                                           constants.UPGRADE_SNAPSHOT_PATH)

            return self.render_to_response(context, status=None)

        action = json_data['properties'].get('action')
        force = json_data['properties'].get('force')
        if action in ['restore', None]:
            return self._restore_snapshot(snapshot_name, force=force,
                                         *args, **kwargs)
        elif action == 'remove':
            return self._delete_snapshot(snapshot_name, force=force,
                                         *args, **kwargs)

    def _delete_snapshot(self, snapshot_name, force=False, *args, **kwargs):
        messages = []
        snapshot_name = snapshot_name or constants.UPGRADE_SNAPSHOT_NAME
        snapshot_path = '%s/%s' % (constants.SNAPSHOT_BASE_PATH, snapshot_name)

        exclude_nodes = kwargs.get('exclude_nodes', None)
        if exclude_nodes is not None:
            messages.extend(
                    self._validate_exclude_nodes(snapshot_name, exclude_nodes))
        if messages:
            url = '/snapshots/%s' % snapshot_name
            status = None
            context = self._parse_messages(messages, url)
            self.get_status_from_messages(messages, status)
            return self.render_to_response(context, status=status)

        remove_force = 'true' if force else 'false'

        snapshot = self.model_manager.get_item(snapshot_path)
        if snapshot:
            snapshot.set_property('force', remove_force)

        exclude_nodes_qi = self._exclude_nodes_query_items(exclude_nodes)
        with utils.set_exclude_nodes(self.execution_manager, exclude_nodes_qi):
            messages = self.execution_manager.delete_snapshot(snapshot_name)

        if isinstance(messages, list):
            context = self._get_context_from_messages(
                messages,
                path=self.model_manager.snapshot_path(snapshot_name),
                action=REMOVE_SNAPSHOT
            )
        else:
            context = self.get_internal_resource(
                    self.get_plan, "plan", recursive_call=True)
        return self.render_to_response(context)

    @check_cannot_create_plan
    @check_plan_not_running
    @request_method_allowed(['DELETE'])
    def delete_snapshot(self, snapshot_name, *args, **kwargs):
        snapshot_path = '%s/%s' % (constants.SNAPSHOT_BASE_PATH, snapshot_name)
        log.trace.warning("'DELETE' operation is deprecated on %s." %
                          snapshot_path)

        return self._delete_snapshot(snapshot_name, *args, **kwargs)

    def _restore_snapshot(self, snapshot_name, force=False, *args, **kwargs):
        messages = []
        if snapshot_name != constants.UPGRADE_SNAPSHOT_NAME:
            messages.append(
                ValidationError(
                    item_path="{0}/{1}".format(
                        constants.SNAPSHOT_BASE_PATH, snapshot_name),
                    error_message='Unsupported snapshot for restore',
                    error_type=constants.INVALID_REQUEST_ERROR
                ).to_dict())

        if not messages:
            self.execution_manager.reset_snapshot_active_attribute()
            if self.execution_manager.snapshot_status(
                             constants.UPGRADE_SNAPSHOT_NAME) == "no_snapshot":
                messages.append(
                    ValidationError(
                        item_path=constants.UPGRADE_SNAPSHOT_PATH,
                        error_message='No Deployment Snapshot to be restored',
                        error_type=constants.INVALID_REQUEST_ERROR
                    ).to_dict())
        else:
            context = self._parse_messages(messages,
                                          constants.UPGRADE_SNAPSHOT_PATH)
            return self.render_to_response(context, status=None)

        if messages:
            context = self._parse_messages(
                                      messages, constants.UPGRADE_SNAPSHOT_PATH
                                           )
            return self.render_to_response(context, status=None)

        self.model_manager.get_item(
                       constants.UPGRADE_SNAPSHOT_PATH
                                    ).set_property('active', 'true')

        context = self._validate_restore_snapshot(
                                               constants.UPGRADE_SNAPSHOT_NAME)
        if context:
            return self.render_to_response(context)

        restore_force = 'true' if force else 'false'

        self.model_manager.get_item(
                      constants.UPGRADE_SNAPSHOT_PATH
                                   ).set_property('force',
                                                   restore_force)

        messages, status, context = self._create_plan_and_return_errors(
            self.execution_manager.restore_snapshot_plan,
            'restore'
        )

        if not messages:
            messages, status = self._run_plan_and_return_errors(status)
        if messages:
            for message in messages:
                if message["error"] != constants.DO_NOTHING_PLAN_ERROR:
                    message["message"] = (
                        "Restore snapshot failed: %s" % message["message"]
                    )
            context = self._parse_messages(messages,
                                           constants.UPGRADE_SNAPSHOT_PATH)
        return self.render_to_response(context, status=status)

    def _litp_snapshot_exists(self):
        return self.model_manager.query('snapshot-base',
                                       item_id=constants.UPGRADE_SNAPSHOT_NAME)

    def _named_snapshots_exist(self):
        all_snapshots = self.model_manager.query('snapshot-base')
        return [ss for ss in all_snapshots if
                                ss.item_id != constants.UPGRADE_SNAPSHOT_NAME]

    def _get_request_body(self, encoded_body, error_list):
        """
          Decodes the json encoded body and, if it is valid, returns the
          data structure included. If not it will append an error to error_list
        """
        try:
            json_data = json.loads(encoded_body)
        except ValueError:
            error_list.append(
                ValidationError(
                  item_path="/plans/plan",
                  error_message='Payload is not valid JSON: %s' % encoded_body,
                  error_type=constants.INVALID_REQUEST_ERROR
                ).to_dict())
            return None
        return json_data

    def _get_context_from_messages(self, messages,
                                   path=constants.SNAPSHOT_BASE_PATH,
                                   action=CREATE_SNAPSHOT):
        for message in messages:
            if message["error"] != constants.DO_NOTHING_PLAN_ERROR:
                message["message"] = (
                    "%s failed: %s" % (action, message["message"])
                )
        return self._parse_messages(messages, path)

    @request_method_allowed(['GET'])
    def get_plan(self, plan_id, **kwargs):
        plan = kwargs.get("validated_plan")
        messages = []
        if plan is None:
            plan = self.execution_manager.plan
            messages = utils.PlanValidator(plan, plan_id).validate()
        if not messages:
            recurse_depth = self._parse_recurse_depth(
                kwargs.get("recurse_depth"))
            if recurse_depth and not isinstance(recurse_depth, int):
                messages.append(recurse_depth)
        if not messages:
            context = {
                "_links": {
                    "self": {
                        "href": self.full_url("/plans/%s" % plan_id)
                    },
                    "item-type": {
                        "href": self.full_url("/item-types/plan")
                    }
                },
                "id": plan_id,
                "item-type-name": "plan",
                "properties": {"state": plan.state},
            }
            ss_status = self.execution_manager.snapshot_status(
                                                constants.UPGRADE_SNAPSHOT_NAME
                                                               )
            basemsg = 'A snapshot of the deployment was completed on'
            ss_model_item = self.model_manager.query(
                       'snapshot-base', item_id=constants.UPGRADE_SNAPSHOT_NAME
                                              )
            if 'exists' in ss_status and ss_model_item:
                ss = ss_model_item[0]
                context["snapshot"] = "{0} {1}".format(
                                    basemsg, utils.human_readable_timestamp(ss)
                                                      )
            elif ss_status == 'failed':
                context["snapshot"] = \
                    "A snapshot of the deployment exists in a failed state"

            if recurse_depth and recurse_depth > 0:
                embedded = self.list_phases(
                        plan_id,
                        recurse_depth=recurse_depth - 1,
                        validated_plan=plan,
                        recursive_call=True)
                context["_embedded"] = {"item": [embedded]}
        else:
            for message in messages:
                message["type"] = message.pop("error", None)
                uri = message.pop("uri", None)
                if uri is not None:
                    message['_links'] = {
                        "self": {"href": self.full_url(uri)}
                    }
            context = {
                "_links": {
                    "self": {"href": self.full_url("/plans/%s" % plan_id)}
                },
                "messages": messages
            }
        if kwargs.get("recursive_call", False):
            return context
        else:
            return self.render_to_response(context)

    def _create_plan_and_return_errors(self, method, snapshot_type, **kwargs):
        status, messages, context = None, [], {}
        result = method(**kwargs)
        if isinstance(result, list):
            messages = result
        elif isinstance(result, BasePlan):
            context = self.get_internal_resource(
                    self.get_plan, "plan", recursive_call=True)
            status = 201
            if snapshot_type:
                if snapshot_type != 'create':
                    status = 200
                # this plan will have an attr saying create, remove or restore
                result.snapshot_type = snapshot_type
        else:
            messages.append(
                ValidationError(
                    item_path=self.model_manager.snapshot_path(
                        kwargs.get('name', '')),
                    error_message="No plan created",
                    error_type=constants.INVALID_REQUEST_ERROR
                ).to_dict()
            )
        return messages, status, context

    def _run_plan_and_return_errors(self, status):
        self.execution_manager.data_manager.commit()
        errors = []
        result = self.execution_manager.run_plan_background()
        if 'error' in result and result['error'] != 'puppet errors':
            errors.append(
                ValidationError(
                    item_path='/plans/plan',
                    error_message=result['error'],
                    error_type=constants.INVALID_REQUEST_ERROR
                ).to_dict()
            )
            status = None
        return errors, status

    def _restore_load_json_data_return_errors(self):
        body_data = cherrypy.request.body.fp.read()
        messages = []
        try:
            json_data = json.loads(body_data)
        except ValueError:
            messages.append(
                ValidationError(
                    item_path=constants.UPGRADE_SNAPSHOT_PATH,
                    error_message='Payload is not valid JSON: %s' % body_data,
                    error_type=constants.INVALID_REQUEST_ERROR
                ).to_dict())
        if self.execution_manager.snapshot_status(
                             constants.UPGRADE_SNAPSHOT_NAME) == "no_snapshot":
            messages.append(
                ValidationError(
                    item_path=constants.UPGRADE_SNAPSHOT_PATH,
                    error_message='No Deployment Snapshot to be restored',
                    error_type=constants.INVALID_REQUEST_ERROR
                ).to_dict())
        return messages, json_data

    def _validate_restore_snapshot(self, snapshot_name):
        errors = []
        if self._named_snapshots_exist():
            errors.append({
              "error": constants.VALIDATION_ERROR,
              "message": "Cannot restore a Deployment Snapshot " +
              "if a Named Backup Snapshot exists."
            })
        elif self.execution_manager.snapshot_status(
                                constants.UPGRADE_SNAPSHOT_NAME) not in \
                                            ('exists', 'exists_previous_plan'):
            errors.append({
                "error": constants.DO_NOTHING_PLAN_ERROR,
                "message": self.execution_manager._get_empty_plan_err(
                    constants.RESTORE_SNAPSHOT_PLAN
            )})
        if errors:
            return self._get_context_from_messages(
                errors,
                path=constants.UPGRADE_SNAPSHOT_NAME,
                action=RESTORE_SNAPSHOT
            )
        return errors

    def _validate_create_snapshot_name(self, name):
        errors = []
        upgrade_snapshot = self.execution_manager.is_upgrade_snapshot(name)
        if self._named_snapshots_exist() and upgrade_snapshot:
            errors.append(ValidationError(
                item_path='/snapshots/%s' % name,
                error_message="Cannot create a Deployment Snapshot if "\
                                     "Named Backup Snapshots exist.",
                error_type=constants.VALIDATION_ERROR).to_dict())
            return errors
        snap_model_item = self.model_manager.query(
            'snapshot-base', item_id=name)
        if snap_model_item:
            if upgrade_snapshot:
                errors.append(ValidationError(
                    item_path='/snapshots/%s' % name,
                    error_message=self.execution_manager.\
                    _get_empty_plan_err(
                        'create_snapshot', name=name),
                    error_type=constants.DO_NOTHING_PLAN_ERROR).to_dict())
            # not intuitive for users to know the name of upgrade snapshots
            else:
                errors.append(ValidationError(
                        item_path='/snapshots/%s' % name,
                        error_message="A snapshot with name \"{0}\" already"\
                                     " exists".format(name),
                        error_type=constants.VALIDATION_ERROR).to_dict())
        if not re.match(r"^[a-zA-Z\d_-]+$", name):
            errors.append(ValidationError(
                        item_path='/snapshots/%s' % name,
                        error_message="A Named Backup Snapshot "\
                            "\"name\" can only contain characters "\
                            "in the range \"[a-zA-Z0-9_-]\"",
                        error_type=constants.VALIDATION_ERROR).to_dict())
        if not upgrade_snapshot:
            if not self.model_manager.backup_exists(
                    LAST_SUCCESSFUL_PLAN_MODEL_ID):
                msg = ("Cannot create named backup snapshot: "
                       "It would not be possible to restore the deployment "
                       "to a known good state because the last "
                       "deployment plan was not successfully executed.")
                errors.append(
                    ValidationError(
                        error_type=constants.VALIDATION_ERROR,
                        error_message=msg).to_dict())
        return errors

    def _validate_and_create_snapshot_item(self, snapshot_name, item_type):
        status = None
        messages = []
        item_path = '/snapshots/%s' % snapshot_name
        item_validation = self.model_manager.check_item_type_registered(
                item_type, item_path)

        if item_validation:
            messages.append(item_validation.to_dict())

        if item_type != self.model_manager.get_item('/snapshots').item_type_id:
            messages.append(ValidationError(
                item_path=item_path,
                error_message="'%s' is not an allowed type for collection "\
                    "of item type 'snapshot-base'" % item_type,
                error_type=constants.INVALID_TYPE_ERROR).to_dict()
            )

        messages.extend(self._validate_create_snapshot_name(snapshot_name))

        if messages:
            # validation errors
            context = self._parse_messages(
                messages,
                self.model_manager.snapshot_path(snapshot_name)
            )
            return self.render_to_response(context, status=status)

        # we should not try to create it if it exists already:
        # create_plan -> creates snapshot item but does not create snapshot
        # create_snapshot -> should not return item exists, but create snapshot
        if self.model_manager.get_item(
                self.model_manager.snapshot_path(snapshot_name)):
            self.model_manager.get_item(
                self.model_manager.snapshot_path(snapshot_name)
                ).set_property('active', 'true')
        else:
            messages = self.model_manager.create_snapshot_item(snapshot_name)
            if not isinstance(messages, ModelItem):
                # error creating the item, return it
                parsed_messages = []
                for msg in messages:
                    parsed_msg = {}
                    parsed_msg['error'] = msg.error_type
                    parsed_msg['uri'] = msg.item_path
                    parsed_msg['message'] = msg.error_message
                    parsed_messages.append(parsed_msg)
                context = self._parse_messages(
                    parsed_messages,
                    self.model_manager.snapshot_path(snapshot_name))
                return self.render_to_response(context, status=status)
        # all ok
        return None

    def stop_plan_validator(self):
        """
          stop plan cannot be run when restore_snapshot is ongoing
        """
        plan = self.execution_manager.plan
        if plan.is_active() and plan.snapshot_type == 'restore':
            return {'error': 'Cannot stop plan when restore is ongoing'}
        return None
