import cherrypy
import json

from litp.core import constants
from litp.service.controllers import LitpControllerMixin
from litp.service.decorators import request_method_allowed


class PropertyTypeController(LitpControllerMixin):

    def __init__(self):
        super(PropertyTypeController, self).__init__()

    @request_method_allowed(['GET'])
    def list_property_types(self):
        property_types = self.model_manager.property_types
        context = {
                "_links": {
                    "self": {
                        "href": self.full_url("/property-types/")
                    }
                },
                "id": "property-types"
            }
        properties = []
        for prop in property_types.iterkeys():
            properties.append(json.loads(self.get_property_type(prop)))
        if properties:
            context["_embedded"] = {"property-type": properties}

        return self.render_to_response(context)

    @request_method_allowed(['GET'])
    def get_property_type(self, property_type_id):
        prop_type = self.model_manager.property_types.get(property_type_id)

        if prop_type is not None:
            context = {
                "_links": {
                    "self": {
                        "href": self.full_url(
                            "/property-types/%s" % property_type_id)
                    }
                },
                "id": property_type_id,
                "regex": prop_type.regex
            }
        else:
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
