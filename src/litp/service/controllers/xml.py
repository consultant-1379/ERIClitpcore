import cherrypy
import re

from lxml.etree import DocumentInvalid
from lxml.etree import XMLSyntaxError

from litp.core import constants
from litp.core.validators import ValidationError
from litp.service.controllers import LitpControllerMixin
from litp.service.decorators import request_method_allowed
from litp.service.decorators import check_plan_not_running
from litp.core.exceptions import XMLExportException


def clean_xml_error_message(message):
    return re.sub(r'Element.*?:(\s+\[.*?\])?\s+(?=\w)', '', message)


class XmlController(LitpControllerMixin):

    def __init__(self):
        super(XmlController, self).__init__()
        self.xml_exporter = cherrypy.config.get("xml_exporter")
        self.xml_loader = cherrypy.config.get("xml_loader")

    def _inspect_plan_structure(self):
        structure = ["/plans"]
        plan = self.execution_manager.plan
        if plan:
            structure.append("/plans/plan")
            structure.append("/plans/plan/phases")
            for index, phase in enumerate(plan.phases):
                curr_phase_path = "/plans/plan/phases/%s" % (index + 1)
                curr_phase_tasks_path = curr_phase_path + "/tasks"
                structure.append(curr_phase_path)
                structure.append(curr_phase_tasks_path)
                for task in phase:
                    structure.append(
                        "/".join((curr_phase_tasks_path, task.task_id)))
        return structure

    def _inspect_meta_structure(self):
        structure = ["/item-types", "/property-types"]
        item_types_paths = [
            '/item-types/%s' % item_type for item_type in
            self.model_manager.item_types.keys()]
        property_types_paths = [
            '/property-types/%s' % property_type for property_type in
            self.model_manager.property_types.keys()]
        structure.extend(item_types_paths)
        structure.extend(property_types_paths)
        return structure

    def _inspect_litp_service_structure(self):
        litp_services = self.model_manager.get_item('/litp')
        structure = []
        if litp_services:
            structure = [litp_services.get_vpath()]
            for child in litp_services.children.values():
                structure.append(child.get_vpath())
        return structure

    @check_plan_not_running
    @request_method_allowed(['GET'])
    def export_xml_item(self, item_path, **kwargs):
        item = self._get_item_from_model_snapshot(item_path)
        item_path = self.normalise_path(item_path)

        disallowed_paths = self._inspect_plan_structure()
        disallowed_paths.extend(self._inspect_meta_structure())
        disallowed_paths.extend(self._inspect_litp_service_structure())
        disallowed_types = ['snapshot-base', 'upgrade']

        if item_path in disallowed_paths or \
           (item and item.item_type_id in disallowed_types):
            return self._error_message(
                message_type=constants.METHOD_NOT_ALLOWED_ERROR,
                message=constants.ERROR_MESSAGE_CODES.get(
                    constants.METHOD_NOT_ALLOWED_ERROR),)
        elif item is None:
            return self._error_message(
                message_type=constants.INVALID_LOCATION_ERROR,
                message="Not Found")

        cherrypy.response.headers["Content-Type"] = "application/xml"
        cherrypy.response.status = constants.OK
        try:
            xml_doc = self.xml_exporter.get_as_xml(item_path)
            if not xml_doc:
                cherrypy.response.status = constants.NOT_FOUND
            return xml_doc
        except XMLExportException as e:
            return self._error_message(
                message_type=constants.METHOD_NOT_ALLOWED_ERROR,
                message=str(e))

    @check_plan_not_running
    @request_method_allowed(['POST'])
    def import_xml_item(self, item_path, **kwargs):
        def invalid_xml_data_error(message="Invalid XML data"):
            error_message = re.sub(r'\{.*?\}', '', message)
            error_message = re.sub(r'(\.,)', ',', error_message)
            return ValidationError(
                item_path=item_path,
                error_message=(error_message),
                error_type=constants.INVALID_REQUEST_ERROR
            ).to_dict()

        item = self._get_item_from_model_snapshot(item_path)
        item_path = self.normalise_path(item_path)
        disallowed_paths = self._inspect_plan_structure()
        disallowed_paths.extend(self._inspect_meta_structure())
        disallowed_paths.extend(self._inspect_litp_service_structure())
        disallowed_types = ['snapshot-base', 'upgrade']

        if item_path in disallowed_paths or \
           (item and item.item_type_id in disallowed_types):
            return self._error_message(
                message_type=constants.METHOD_NOT_ALLOWED_ERROR,
                message=constants.ERROR_MESSAGE_CODES.get(
                    constants.METHOD_NOT_ALLOWED_ERROR))
        elif item is None:
            return self._error_message(
                message_type=constants.INVALID_LOCATION_ERROR,
                message="Not Found")

        body_data = cherrypy.request.body.fp.read()
        xml_loader = cherrypy.config.get("xml_loader")
        errors = []
        messages = None
        try:
            merge = bool(kwargs.get("merge", False))
            replace = bool(kwargs.get("replace", False))
            messages = xml_loader.load(item_path, body_data,
                                       merge=merge, replace=replace)
            for err in messages:
                if isinstance(err, ValidationError):
                    err_dict = err.to_dict()
                    err_dict['message'] = clean_xml_error_message(
                        err_dict['message']
                    )
                    errors.append(err_dict)
                else:
                    errors.append(err)
        except DocumentInvalid as di:
            errors.append(invalid_xml_data_error(message=di.message))
        except XMLSyntaxError as se:
            message = str(se) if se.args and se.args[0] else None
            if not message:
                message = "invalid xml data"
            errors.append(invalid_xml_data_error(message))

        context = {}
        if errors:
            self.data_manager.rollback()
            for message in errors:
                message["type"] = message.get("error", None)
                uri = message.get("uri", None)
                if uri is not None:
                    if message["type"] == constants.INVALID_LOCATION_ERROR:
                        location = uri
                    else:
                        location = self.full_url(uri)
                    message['_links'] = {
                        "self": {"href": location}
                    }
            context = {
                "_links": {
                    "self": {"href": self.full_url(item_path)}
                },
                "messages": errors
            }
        else:
            self.execution_manager.model_changed()
        return self.render_to_response(context)

    def _error_message(self, message_type, message):
        context = {
            "messages": [
                {
                    "_links": {
                        "self": {
                            "href": cherrypy.request.path_info
                        }
                    },
                    "type": message_type,
                    "message": message
                }
            ]
        }
        return self.render_to_response(context)
