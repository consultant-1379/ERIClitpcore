import cherrypy
import json

from litp.core import constants
from litp.core.model_type import View
from litp.service import utils
from litp.service.controllers import LitpControllerMixin
from litp.service.decorators import request_method_allowed


class ItemTypeController(LitpControllerMixin):

    def __init__(self):
        super(ItemTypeController, self).__init__()

    @request_method_allowed(['GET'])
    def list_item_types(self):
        item_types = self.model_manager.item_types
        context = {
                "_links": {
                    "self": {
                        "href": self.full_url("/item-types/")
                    }
                },
                "id": "item-types"
            }
        embedded = []
        for item_name in item_types.iterkeys():
            embedded.append(json.loads(
                self.get_item_type(item_name, include_embedded=False)))
        if embedded:
            context["_embedded"] = {"item-type": embedded}

        return self.render_to_response(context)

    @request_method_allowed(['GET'])
    def get_item_type(self, item_type_id, **kwargs):
        item_type = self.model_manager.item_types.get(item_type_id)

        if item_type is not None:
            context = {
                "_links": {
                    "self": {
                        "href": self.full_url("/item-types/%s" % item_type_id)
                    }
                },
                "id": item_type_id
            }
            if hasattr(item_type, "item_description"):
                context["description"] = item_type.item_description

            if item_type.extend_item:
                context["_links"].update({"base-type": {
                    "href": self.full_url(
                        "/item-types/%s" % item_type.extend_item)
                }})
            fields = {}
            properties = {}
            for field_name, field_obj in item_type.structure.iteritems():
                if field_name in \
                   item_type.get_properties():
                    field = item_type.structure.get(field_name)
                    prop_context = self._get_item_type_property(
                                            field.item_type_id)
                    if (hasattr(field, "required") and
                        field.required is not None):
                        prop_context["required"] = field.required
                    if hasattr(field, "default") and field.default is not None:
                        prop_context["default"] = field.default
                    if (hasattr(field, "item_description") and
                            field.item_description is not None):
                        prop_context["description"] = field.item_description
                    if (hasattr(field, "site_specific") and
                            field.site_specific is not None):
                        prop_context["site_specific"] = field.site_specific
                    properties[field_name] = prop_context
                elif not isinstance(field_obj, View):
                    fields[field_name] = field_obj
            if properties:
                context["properties"] = properties
            if kwargs.get("include_embedded", True):
                items = []
                for field_name in fields.iterkeys():
                    items.append(self._get_item_type_field(
                        item_type_id, field_name, include_embedded=False))
                if items:
                    context["_embedded"] = {"item": items}
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
                    "message": "Not found"
                }]
            }
        return self.render_to_response(context)

    def _get_item_type_property(self, property_type_id, **kwargs):
        prop_type = self.model_manager.property_types.get(property_type_id)
        context = {
            "_links": {
                "self": {
                    "href": self.full_url(
                        "/property-types/%s" % prop_type.property_type_id)
                }
            },
            "id": property_type_id,
            "regex": prop_type.regex
        }
        return context

    def _get_item_type_field(self, item_type_id, field_name, **kwargs):
        item_type = self.model_manager.item_types.get(item_type_id)
        field_item = item_type.structure.get(field_name)
        field_manager = utils.FieldManager()
        links = field_manager.get_context(field_name, field_item)
        for key in links.keys():
            links[key] = {"href": self.full_url(links[key]["href"])}
        context = {
            "_links": {},
            "id": field_name
        }
        context["_links"].update(links)
        if hasattr(field_item, "required"):
            context["required"] = field_item.required
        if hasattr(field_item, "properties") and field_item.properties:
            context["properties"] = field_item.properties
        if hasattr(field_item, "item_description"):
            context["description"] = field_item.item_description
        if hasattr(field_item, "default"):
            context["default"] = field_item.default
        if hasattr(field_item, "min_count"):
            context["min"] = field_item.min_count
        if hasattr(field_item, "max_count"):
            context["max"] = field_item.max_count
        return context
