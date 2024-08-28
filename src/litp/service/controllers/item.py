import cherrypy
import json

from litp.core import constants
from litp.core.model_item import ModelItem
from litp.core.validators import ValidationError
from litp.service import utils
from litp.service.controllers import LitpControllerMixin
from litp.service.decorators import request_method_allowed
from litp.service.decorators import check_plan_not_running
from litp.service.utils import get_db_availability

from litp.core.litp_logging import LitpLogger
log = LitpLogger()


class ItemController(LitpControllerMixin):

    def __init__(self):
        super(ItemController, self).__init__()

    @request_method_allowed(['GET'])
    def get_item(self, item_path, **kwargs):
        context = None
        try:
            item = self._get_item_from_model_snapshot(item_path)
            if item is not None:
                context = self.generate_hal_context(
                        item,
                        item.children.values()
                    )
            else:
                context = {
                    "_links": {
                        "self": {"href": self.full_url(item_path)}
                    },
                    "messages": [{
                        "_links": {
                            "self": {"href": self.full_url(item_path)}
                        },
                        "type": constants.INVALID_LOCATION_ERROR,
                        "message": "Not found",
                    }]
                }
        except Exception as caught:  # pylint: disable=W0703
            if not get_db_availability():
                raise caught
            log.trace.error(
                "Exception while reading an item: '%s'" % str(caught))
            error = ValidationError(
                    item_path=item_path,
                    error_message="An exception occurred while reading this "
                        "item.",
                    error_type=constants.INTERNAL_SERVER_ERROR
                )

            context = {
                "_links": {
                    "self": {"href": self.full_url(item_path)}
                }
            }

            message = error.to_dict()
            message["type"] = message.pop("error", None)
            uri = message.pop("uri", None)
            if uri is not None:
                message['_links'] = {
                    "self": {"href": self.full_url(uri)}
                }
            context["messages"] = [message]
        return self.render_to_response(context)

    @check_plan_not_running
    @request_method_allowed(['POST'])
    def create_json_item(self, item_path, **kwargs):
        status = None
        item_path = self.normalise_path(item_path)
        body_data = cherrypy.request.body.fp.read()
        messages = []
        try:
            json_data = json.loads(body_data)
            if json_data.get('type', '') in ['upgrade']:
                return self.type_not_allowed(json_data['type'])
        except ValueError:
            messages.append(
                ValidationError(
                    item_path=item_path,
                    error_message='Payload is not valid JSON: %s' % body_data,
                    error_type=constants.INVALID_REQUEST_ERROR
                ).to_dict())
        if not messages:
            validator = utils.ItemPayloadValidator(json_data, item_path)
            messages = validator.validate()
        if not messages:
            item_properties = json_data.get('properties', {})

            if item_path != '/':
                item_path = '/'.join([item_path, json_data['id']])
            else:
                item_path = ''.join([item_path, json_data['id']])

            try:
                if 'type' in json_data:
                    result = self.model_manager.create_item(
                        json_data['type'], item_path, **item_properties)
                elif 'inherit' in json_data:
                    result = self.model_manager.create_inherited(
                        json_data['inherit'], item_path, **item_properties
                    )

                if isinstance(result, ModelItem):
                    context = self.generate_hal_context(
                        result, result.children.values())
                    self.execution_manager.model_changed()
                    status = 201
                else:
                    messages.extend([err.to_dict() for err in result])

            except Exception as caught:  # pylint: disable=W0703
                if not get_db_availability():
                    raise caught
                log.trace.error(
                    "Exception while creating an item: '%s'" % str(caught))
                error = ValidationError(
                        item_path=item_path,
                        error_message="An exception occurred while creating "
                            "this item.",
                        error_type=constants.INTERNAL_SERVER_ERROR
                    )
                messages.append(error.to_dict())

        if messages:
            context = {
                "_links": {
                    "self": {"href": self.full_url(item_path)}
                }
            }
            for message in messages:
                message["type"] = message.pop("error", None)
                uri = message.pop("uri", None)
                if uri is not None:
                    message['_links'] = {
                        "self": {"href": self.full_url(uri)}
                    }
                if message["type"] == constants.ITEM_EXISTS_ERROR:
                    context = json.loads(
                        self.get_internal_resource(self.get_item, item_path))
            context["messages"] = messages

        return self.render_to_response(context, status=status)

    @check_plan_not_running
    @request_method_allowed(['PUT'])
    def update_item(self, item_path, **kwargs):
        messages = []
        try:
            item = self._get_item_from_model_snapshot(item_path)
        except Exception as caught:  # pylint: disable=W0703
            if not get_db_availability():
                raise caught
            log.trace.error(
                "Exception while reading an item: '%s'" % str(caught))
            error = ValidationError(
                    item_path=item_path,
                    error_message="An exception occurred while reading this "
                        "item.",
                    error_type=constants.INTERNAL_SERVER_ERROR
                )
            messages.append(error.to_dict())

        item_path = self.normalise_path(item_path)
        if item is None:
            messages.append(
                ValidationError(
                    item_path=item_path,
                    error_message='Not found',
                    error_type=constants.INVALID_LOCATION_ERROR
                ).to_dict())
        else:
            body_data = cherrypy.request.body.fp.read()
            try:
                json_data = json.loads(body_data)
            except ValueError:
                messages.append(
                    ValidationError(
                        item_path=item_path,
                        error_message=(
                            'Payload is not valid JSON: %s' % body_data
                        ),
                        error_type=constants.INVALID_REQUEST_ERROR
                    ).to_dict())
            if not messages:
                item_properties = json_data.get('properties', {})
                if item_properties:
                    try:
                        result = self.model_manager.update_item(
                            item_path, **item_properties)
                        if isinstance(result, ModelItem):
                            context = self.generate_hal_context(
                                result, result.children.values())
                            self.execution_manager.model_changed()
                        else:
                            messages.extend([err.to_dict() for err in result])
                    except Exception as caught:  # pylint: disable=W0703
                        if not get_db_availability():
                            raise caught
                        log.trace.error(
                            "Exception while updating an item: '%s'" % \
                            str(caught)
                        )
                        error = ValidationError(
                                item_path=item_path,
                                error_message="An exception occurred while "
                                    "updating this item.",
                                error_type=constants.INTERNAL_SERVER_ERROR
                            )
                        messages.append(error.to_dict())
                else:
                    msg = "Properties must be specified for update"
                    messages.append(
                        ValidationError(
                            item_path=item_path,
                            error_message=msg,
                            error_type=constants.INVALID_REQUEST_ERROR
                        ).to_dict())

        if messages:
            for message in messages:
                message["type"] = message.pop("error", None)
                uri = message.pop("uri", None)
                if uri is not None:
                    message['_links'] = {
                        "self": {"href": self.full_url(uri)}
                    }
            context = {
                "_links": {
                    "self": {"href": self.full_url(item_path)}
                }
            }
            if item is not None:
                context = json.loads(
                    self.get_internal_resource(self.get_item, item_path))
            context["messages"] = messages
        return self.render_to_response(context)

    @check_plan_not_running
    @request_method_allowed(['DELETE'])
    def delete_item(self, item_path, **kwargs):
        item_path = self.normalise_path(item_path)
        errors = []
        try:
            item = self.model_manager.get_item(item_path)
            if item:
                parent = item.parent
            result = self.model_manager.remove_item(item_path)
            if isinstance(result, ModelItem):
                context = self.generate_hal_context(
                    parent, parent.children.values())
                self.execution_manager.model_changed()
            else:
                errors.extend([err.to_dict() for err in result])

        except Exception as caught:  # pylint: disable=W0703
            if not get_db_availability():
                raise caught
            log.trace.error(
                "Exception while deleting an item: '%s'" % str(caught))
            error = ValidationError(
                    item_path=item_path,
                    error_message="An exception occurred while "
                        "deleting this item.",
                    error_type=constants.INTERNAL_SERVER_ERROR
                )
            errors.append(error.to_dict())

        finally:
            if errors:
                for err in errors:
                    err["type"] = err.pop("error", None)
                    uri = err.pop("uri", None)
                    if uri is not None:
                        err['_links'] = {
                            "self": {"href": self.full_url(uri)}
                        }
                context = json.loads(
                    self.get_internal_resource(self.get_item, item_path))
                context["messages"] = errors
        return self.render_to_response(context)
