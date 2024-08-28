import json
from logging import DEBUG

from litp.core import constants
from litp.core.litp_logging import LitpLogger
from litp.core.validators import ValidationError
from litp.service import utils
from litp.service.controllers import LitpControllerMixin
from litp.service.decorators import request_method_allowed

log = LitpLogger()


class BasePlanController(LitpControllerMixin):

    @request_method_allowed(['GET'])
    def list_plans(self, **kwargs):
        context = {
            "_links": {
                "self": {
                    "href": self.full_url("/plans")
                },
                "collection-of": {
                    "href": self.full_url("/item-types/plan")
                }
            },
            "id": "plans",
            "item-type-name": "collection-of-plan"
        }
        if self.execution_manager.plan:
            recurse_depth = kwargs.get("recurse_depth")
            recurse_depth = self._parse_recurse_depth(recurse_depth)
            if isinstance(recurse_depth, int):
                embedded = self.get_plan("plan",
                    recurse_depth=recurse_depth - 1,
                    recursive_call=True)
                context["_embedded"] = {"item": [embedded]}
            else:
                recurse_depth['_links'] = {
                    "self": {"href": self.full_url("/plans")}
                }
                context = {
                    "_links": {
                        "self": {"href": self.full_url("/plans")}
                    },
                    "messages": recurse_depth
                }
        return self.render_to_response(context)

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

            if log.log_level() == DEBUG:
                context["plan_phase_tree"] = plan.phase_tree_graph

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

    def stop_plan_validator(self):
        """
          stop plan cannot be run when restore_snapshot is ongoing
        """
        plan = self.execution_manager.plan
        if plan.is_active() and plan.snapshot_type == 'restore':
            return {'error': 'Cannot stop plan when restore is ongoing'}
        return None

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

    def _parse_messages(self, messages, item_url):
        for message in messages:
            message["type"] = message.pop("error", None)
            uri = message.pop("uri", None)
            if uri is not None:
                message['_links'] = {
                    "self": {"href": self.full_url(uri)}
                }
        context = {
            "_links": {
                "self": {"href": self.full_url(item_url)}
            },
            "messages": messages
        }
        return context

    def list_phases(self, plan_id, **kwargs):
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
                        "href": self.full_url("/plans/%s/phases" % plan_id)
                    },
                    "collection-of": {
                        "href": self.full_url("/item-types/phase")
                    }
                },
                "id": "phases",
                "item-type-name": "collection-of-phase"
            }
            if recurse_depth and recurse_depth > 0:
                phases = []
                phases_count = len(plan.phases)
                for index in xrange(1, phases_count + 1):
                    phases.append(
                        self.get_phase(
                            plan_id,
                            index,
                            recurse_depth=recurse_depth - 1,
                            validated_plan=plan,
                            recursive_call=True))
                if phases:
                    context["_embedded"] = {"item": phases}
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
                    "self": {"href": self.full_url(
                        "/plans/%s/phases" % plan_id)}
                },
                "messages": messages
            }
        if kwargs.get("recursive_call", False):
            return context
        else:
            return self.render_to_response(context)

    def get_phase(self, plan_id, phase_id, **kwargs):
        plan = kwargs.get("validated_plan")
        messages = []
        if plan is None:
            plan = self.execution_manager.plan
            messages = utils.PhaseValidator(plan, plan_id, phase_id).validate()
        if not messages:
            recurse_depth = self._parse_recurse_depth(
                kwargs.get("recurse_depth"))
            if recurse_depth and not isinstance(recurse_depth, int):
                messages.append(recurse_depth)
        if not messages:
            context = {
                "_links": {
                    "self": {
                        "href": self.full_url(
                            "/plans/%s/phases/%s" % (plan_id, phase_id))
                    },
                    "item-type": {
                        "href": self.full_url("/item-types/phase")
                    }
                },
                "id": phase_id,
                "item-type-name": "phase"
            }
            if recurse_depth and recurse_depth > 0:
                if isinstance(recurse_depth, int):
                    embedded = self.list_tasks(
                            plan_id,
                            phase_id,
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
                    "self": {"href": self.full_url(
                        "/plans/%s/phases/%s" % (plan_id, phase_id))}
                },
                "messages": messages
            }
        if kwargs.get("recursive_call", False):
            return context
        else:
            return self.render_to_response(context)

    def list_tasks(self, plan_id, phase_id, **kwargs):
        plan = kwargs.get("validated_plan")
        messages = []
        if plan is None:
            plan = self.execution_manager.plan
            messages = utils.PhaseValidator(plan, plan_id, phase_id).validate()
        if not messages:
            recurse_depth = self._parse_recurse_depth(
                kwargs.get("recurse_depth"))
            if recurse_depth and not isinstance(recurse_depth, int):
                messages.append(recurse_depth)
        if not messages:
            context = {
                "_links": {
                    "self": {
                        "href": self.full_url("/plans/%s/phases/%s/tasks" %
                            (plan_id, phase_id))
                    },
                    "collection-of": {
                        "href": self.full_url("/item-types/task")
                    }
                },
                "id": "tasks",
                "item-type-name": "collection-of-task"
            }
            if recurse_depth and recurse_depth > 0:
                tasks_list = plan.get_phase(int(phase_id) - 1)
                tasks = []
                for task in tasks_list:
                    tasks.append(
                        self.get_task(
                            plan_id, phase_id,
                            task._id,
                            recurse_depth=recurse_depth - 1,
                            validated_plan=plan,
                            recursive_call=True))
                if tasks:
                    context["_embedded"] = {"item": tasks}
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
                    "self": {"href": self.full_url(
                        "/plans/%s/phases/%s/tasks" % (plan_id, phase_id))}
                },
                "messages": messages
            }
        if kwargs.get("recursive_call", False):
            return context
        else:
            return self.render_to_response(context)

    def get_task(self, plan_id, phase_id, task_id, **kwargs):
        task = self.data_manager.get_task(task_id)
        if task is None:
            plan = kwargs.get("validated_plan")
            messages = []
            if plan is None:
                plan = self.execution_manager.plan
                messages = utils.TaskValidator(
                    plan, plan_id, phase_id, task_id).validate()
            for message in messages:
                message["type"] = message.pop("error", None)
                uri = message.pop("uri", None)
                if uri is not None:
                    message['_links'] = {
                        "self": {"href": self.full_url(uri)}
                    }
            context = {
                "_links": {
                    "self": {"href": self.full_url(
                        "/plans/%s/phases/%s/tasks/%s" %
                        (plan_id, phase_id, task_id))}
                },
                "messages": messages
            }
        else:
            context = {
                "_links": {
                    "self": {
                        "href": self.full_url("/plans/%s/phases/%s/tasks/%s" %
                            (plan_id, phase_id, task._id))
                    },
                    "item-type": {
                        "href": self.full_url("/item-types/task")
                    },
                    "rel": {
                        "href": self.full_url(task.item_vpath)
                    }
                },
                "id": task._id,
                "item-type-name": "task",
                "state": task.state,
                "description": task.description
            }
            if hasattr(task, "call_id"):
                context["call_id"] = task.call_id
            if hasattr(task, "call_type"):
                context["call_type"] = task.call_type
        if kwargs.get("recursive_call", False):
            return context
        else:
            return self.render_to_response(context)
