import cherrypy

from litp.core import constants
from litp.service.controllers import LitpControllerMixin
from litp.core.validators import ValidationError


def create_error_list(err_type, message, path=None):
    return [
            ValidationError(
                item_path=path,
                error_message=message,
                error_type=err_type
            )
        ]


class MiscController(LitpControllerMixin):

    def __init__(self):
        super(MiscController, self).__init__()

    def default_route(self, path_info):
        context = {
                "_links": {
                    "self": {
                        "href": self.full_url(cherrypy.request.path_info)
                    }
                },
                "messages": [{
                    "_links": {
                        "self": {
                            "href": self.full_url(cherrypy.request.path_info)
                        }
                    },
                    "type": constants.INVALID_LOCATION_ERROR,
                    "message": ("Not found")
                }]
            }
        return self.render_to_response(context)
