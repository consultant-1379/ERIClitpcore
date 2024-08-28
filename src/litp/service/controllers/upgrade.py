import cherrypy
import json
from litp.service.controllers import LitpControllerMixin
from litp.service.decorators import request_method_allowed,\
                                    check_plan_not_running
from litp.core.model_manager import ModelManagerException
from litp.core.constants import INVALID_LOCATION_ERROR


class UpgradeController(LitpControllerMixin):

    @check_plan_not_running
    @request_method_allowed(['POST'])
    def upgrade(self, item_path, **kwargs):
        json_data = json.loads(cherrypy.request.body.fp.read())
        path, sha = json_data.get('path'), \
                    json_data.get('hash')
        try:
            errors = self.model_manager.handle_upgrade_item(path, sha)
        except ModelManagerException:
            context = {
                "_links": {
                    "self": {"href": self.full_url(path)}
                },
                "messages": [{
                    "_links": {
                        "self": {"href": self.full_url(path)}
                },
                "type": INVALID_LOCATION_ERROR,
                "message": "Upgrade can only be run on deployments, clusters"\
                           " or nodes",
                }]
            }
            return self.render_to_response(context, status=None)
        if errors:
            dict_errors = [errors.to_dict()]
            context = self._parse_messages(dict_errors, item_path)
            return self.render_to_response(context, status=None)
        else:
            self.execution_manager.model_changed()
            return self.render_to_response({}, status=201)

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
