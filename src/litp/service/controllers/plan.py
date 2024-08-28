import cherrypy
import json
import re

from litp.core import constants
from litp.core.litp_logging import LitpLogger
from litp.core.policies import LockPolicy
from litp.core.plan import BasePlan
from litp.core.validators import ValidationError
from litp.service import utils
from litp.service.controllers.baseplan import BasePlanController
from litp.service.decorators import request_method_allowed

log = LitpLogger()


class PlanController(BasePlanController):

    def nmp_create_validator(self, some_path):
        validation_errors = []
        msg, err_type = self._get_cannot_create_plan_errs()
        if not self.execution_manager.plan_exists():
            validation_errors.append(
                ValidationError(
                    item_path=some_path,
                    error_message=msg,
                    error_type=err_type).to_dict()
            )
        elif not self.execution_manager.can_create_plan():
            if self.execution_manager.is_plan_running():
                validation_errors.append(
                    ValidationError(
                        item_path=some_path,
                        error_message=(msg),
                        error_type=err_type).to_dict()
            )
            elif self.execution_manager.is_plan_stopping():
                validation_errors.append(
                    ValidationError(
                        item_path=some_path,
                        error_message=(msg),
                        error_type=err_type).to_dict()
            )
        return validation_errors

    def nmp_delete_validator(self, some_path):
        validation_errors = []
        if self.execution_manager.plan_exists():
            if self.execution_manager.plan.is_running() or\
                self.execution_manager.plan.is_stopping():
                validation_errors.append(
                    ValidationError(
                        item_path=some_path,
                        error_message=(
                            "Removing a running/stopping plan is not allowed"),
                        error_type=constants.INVALID_REQUEST_ERROR).to_dict()
                )
        return validation_errors

    def nmp_run_validator(self, resume):
        """
          Check if a plan can be run (must exist and be in initial state)
        """
        if not self.execution_manager.plan_exists():
            return {'error': 'Plan does not exist'}

        plan = self.execution_manager.plan
        if plan.is_active():
            log.trace.info('Trying to run plan that is already active.')
            return {'error': 'Plan is currently running or stopping'}

        if resume:
            # see TORF-306119.That + [''] is tech debt that should be addressed
            if plan.plan_type in constants.SNAPSHOT_PLANS + ['']:
                msg = 'Cannot resume a snapshot plan'
                return {'error': msg}

            if plan.state == BasePlan.FAILED:
                log.event.info(
                    'Resuming plan in state "%s".',
                        BasePlan.FAILED)
                return None
            else:
                log.trace.info('Trying to resume plan in state %s', plan.state)
                msg = 'Cannot resume plan in state "%s"' % plan.state
                return {'error': msg}
        else:
            if plan.is_initial():
                return None
            log.trace.info('Trying to run plan that is not in initial state.')
            if plan.state == BasePlan.INVALID:
                msg = 'Plan is invalid - model changed'
            else:
                msg = 'Plan not in initial state'
            return {'error': msg}

    def _validate_resume_property(self, json_data):
        validation_errors = []
        try:
            resume_value = json_data["properties"]["resume"]
            pattern = re.compile(r'^(true|false)$')
            if pattern.match(resume_value) is None:
                msg = (
                    "Invalid value for resume specified: '%s'" % resume_value
                )
                validation_errors.append(
                    ValidationError(
                        item_path="/plans/plan",
                        error_message=msg,
                        error_type=constants.INVALID_REQUEST_ERROR
                    ).to_dict()
                )
        except KeyError:
            pass

        return validation_errors

    @request_method_allowed(['POST'])
    def create_plan(self, *args, **kwargs):
        body_data = cherrypy.request.body.fp.read()
        status = None
        messages = []
        json_data = self._get_request_body(body_data, messages)
        if not messages:
            messages = utils.PlanPayloadValidator(json_data).validate()
        if not messages:
            plan_id = json_data.get('id', None)
            plan_type = json_data.get('type', None)
            node_path = json_data.get('path', None)
            if plan_type != 'reboot_plan':
                # a reboot plan should not reset the active attr in a snapshot
                self.execution_manager.reset_snapshot_active_attribute()
            no_lock_tasks = json_data.get('no-lock-tasks', False)
            no_lock_tasks_list = json_data.get('no-lock-tasks-list', [])
            initial_lock_tasks = json_data.get('initial-lock-tasks', False)

            lock_policies = []
            lock_policy1 = None
            #Create lock/unlock tasks
            if not no_lock_tasks and not initial_lock_tasks:
                lock_policies.append(LockPolicy(LockPolicy.CREATE_LOCKS))

            else:
                if no_lock_tasks and len(no_lock_tasks_list) > 0:
                    lock_policy1 = LockPolicy(LockPolicy.CREATE_LOCKS,
                    no_lock_tasks_list)

                if no_lock_tasks and len(no_lock_tasks_list) == 0:
                    lock_policy1 = LockPolicy(LockPolicy.NO_LOCKS,
                    no_lock_tasks_list)

                if lock_policy1:
                    lock_policies.append(lock_policy1)

                if initial_lock_tasks:
                    initial_lock_policy = LockPolicy(LockPolicy.INITIAL_LOCKS)
                    lock_policies.append(initial_lock_policy)

            if self.execution_manager.can_create_plan():
                # due to PlanPlayloadValidator validation plan_type can only be
                # plan or reboot_plan
                result = self.execution_manager.create_plan(
                    plan_type=constants.DEPLOYMENT_PLAN if
                            plan_type == 'plan' else
                            constants.REBOOT_PLAN,
                    lock_policies=lock_policies,
                    node_path=node_path if node_path else '',
                )
                if isinstance(result, list):
                    messages = result
                elif isinstance(result, BasePlan):
                    context = self.get_internal_resource(
                        self.get_plan, plan_id, recursive_call=True)
                    status = 201
                else:
                    msg = "No plan created"
                    messages.append(
                        ValidationError(
                            item_path='/plans/' + plan_id,
                            error_message=msg,
                            error_type=constants.INVALID_REQUEST_ERROR
                        ).to_dict()
                    )
            else:
                messages.extend(self.nmp_create_validator('/plans/' + plan_id))
        if messages:
            for message in messages:
                message["type"] = message.pop("error", None)
                message["message"] = "Create plan failed: " + \
                        message["message"]
                uri = message.pop("uri", None)
                if uri is not None:
                    message['_links'] = {
                        "self": {"href": self.full_url(uri)}
                    }
            context = {
                "_links": {
                    "self": {"href": self.full_url("/plans/")}
                },
                "messages": messages
            }
        return self.render_to_response(context, status=status)

    @request_method_allowed(['PUT'])
    def update_plan(self, plan_id, **kwargs):
        body_data = cherrypy.request.body.fp.read()
        plan = self.execution_manager.plan
        messages = []
        try:
            json_data = json.loads(body_data)
        except ValueError:
            messages.append(
                ValidationError(
                    item_path="/plans/plan",
                    error_message='Payload is not valid JSON: %s' % body_data,
                    error_type=constants.INVALID_REQUEST_ERROR
                ).to_dict())
        if not messages:
            messages = utils.UpdatePlanPayloadValidator(
                plan, plan_id, json_data).validate()
            messages += self._validate_resume_property(json_data)

        if not messages:
            plan_state = json_data["properties"]["state"]
            if plan_state == BasePlan.RUNNING:
                resume = False
                if "resume" in json_data["properties"]:
                    resume = (json_data["properties"]["resume"] == "true")

                result = self.nmp_run_validator(resume)
                if not result:
                    if resume:
                        self.execution_manager.fix_removed_items_on_resume()
                    result = self.execution_manager.run_plan_background()
            elif plan_state == BasePlan.STOPPED:
                result = self.stop_plan_validator()
                if not result:
                    result = self.execution_manager.stop_plan()
            else:
                result = {'error': 'Unsupported plan state %s' % plan_state}
            if 'error' in result and result['error'] != 'puppet errors':
                msg = result['error']
                messages.append(
                    ValidationError(
                        item_path='/plans/plan',
                        error_message=msg,
                        error_type=constants.INVALID_REQUEST_ERROR
                    ).to_dict()
                )
            context = self.get_internal_resource(
                    self.get_plan, plan_id, recursive_call=True)
        if messages:
            context = self._parse_messages(messages, "/plans/%s" % plan_id)
        return self.render_to_response(context)

    @request_method_allowed(['DELETE'])
    def delete_plan(self, plan_id, **kwargs):
        context = {}
        plan = self.execution_manager.plan
        messages = self.nmp_delete_validator('/plans/' + plan_id)
        messages.extend(utils.PlanValidator(plan, plan_id).validate())

        if not messages:
            self.execution_manager.delete_plan()
            context = json.loads(self.get_internal_resource(self.list_plans))
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

        return self.render_to_response(context)
