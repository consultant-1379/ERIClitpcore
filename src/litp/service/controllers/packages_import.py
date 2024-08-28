import cherrypy
import json
from litp.service.controllers import LitpControllerMixin
from litp.service.decorators import request_method_allowed
from litp.core.packages_import import PackagesImport
from litp.core.validators import ValidationError
from litp.service.decorators import check_plan_not_running


class PackagesImportController(LitpControllerMixin):
    def packages_import(self, json_data):
        source_path = json_data["source_path"]
        destination_path = json_data["destination_path"]

        packages = PackagesImport(
            source_path,
            destination_path,
            self.execution_manager
        )
        errors = []
        messages = packages.run_import()
        if messages:
            for err in messages:
                if isinstance(err, ValidationError):
                    errors.append(err.to_dict())
        context = {}
        if errors:
            context = self._create_context_from_errors(errors)

        return self.render_to_response(context)

    def _create_context_from_errors(self, errors):
        for message in errors:
            message["type"] = message.pop("error", None)
            uri = message.pop("uri", None)
            if uri is not None:
                message['_links'] = {
                    "self": {"href": "/import"}
                }
        return {
            "_links": {
                "self": {"href": "/import"}
            },
            "messages": errors
        }

    @check_plan_not_running
    @request_method_allowed(['PUT'])
    def handle_import(self):
        body_data = cherrypy.request.body.fp.read()
        json_data = json.loads(body_data)
        return self.packages_import(json_data)
