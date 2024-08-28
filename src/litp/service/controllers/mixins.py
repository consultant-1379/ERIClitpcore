import cherrypy
import os
from operator import itemgetter

import litp.service
from litp.core import scope
from litp.core import constants
from litp.core.validators import ValidationError
from litp.core.model_item import CollectionItem
from litp.core.model_item import RefCollectionItem
from litp.service.template.loaders import FilesystemLoader
from litp.service.utils import get_litp_packages, get_litp_version

BASE_DIR = os.path.dirname(os.path.abspath(litp.service.__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")


class LitpControllerMixin(object):

    def __init__(self, templates_dir=None):
        if templates_dir is None:
            templates_dir = TEMPLATES_DIR

        self.loader = FilesystemLoader(templates_dir)

    @property
    def model_manager(self):
        return cherrypy.config["model_manager"]

    @property
    def data_manager(self):
        return scope.data_manager

    @property
    def execution_manager(self):
        return cherrypy.config["execution_manager"]

    @property
    def puppet_manager(self):
        return cherrypy.config["puppet_manager"]

    @property
    def plugin_manager(self):
        return self.execution_manager.plugin_manager

    @staticmethod
    def allows_maintenance():
        return False

    def full_url(self, rel_path):
        if cherrypy.request.base in rel_path:
            return rel_path

        rel_path = self.normalise_path(rel_path)
        tokens = [cherrypy.request.base]

        if cherrypy.request.script_name:
            tokens.append(cherrypy.request.script_name)

        tokens.append(rel_path)

        return ''.join(tokens)

    def method_not_allowed(self, item_path=None):
        context = {
            "_links": {
                "self": {"href": self.full_url(cherrypy.request.path_info)}
            },
            "messages": [
                {
                    "_links": {
                        "self": {
                            "href": self.full_url(cherrypy.request.path_info)
                        }
                    },
                    "type": "MethodNotAllowedError",
                    "message": (
                        "%s method on path not allowed"
                        % self._decode(cherrypy.request.method))
                }
            ]
        }
        return self.render_to_response(context)

    def type_not_allowed(self, type_id):
        context = {
            "_links": {
                "self": {"href": self.full_url(cherrypy.request.path_info)}
            },
            "messages": [
                {
                    "_links": {
                        "self": {
                            "href": self.full_url(cherrypy.request.path_info)
                        }
                    },
                    "type": "TypeNotAllowedError",
                    "message": (
                        "%s method on type %s not allowed. Please use the "
                        "appropriate LITP command."
                        % (self._decode(cherrypy.request.method), type_id))
                }
            ]
        }
        return self.render_to_response(context)

    def method_not_allowed_blank(self):
        return self.method_not_allowed()

    def invalid_header(self, item_path=None, **kwargs):
        header_value = cherrypy.request.headers.get("Content-Type", "None")
        context = {
            "_links": {
                "self": {"href": self.full_url(cherrypy.request.path_info)}
            },
            "messages": [
                {
                    "_links": {
                        "self": {
                            "href": self.full_url(cherrypy.request.path_info)
                        }
                    },
                    "type": constants.HEADER_NOT_ACCEPTABLE_ERROR,
                    "message": (
                        "Invalid 'Content-Type' header value: %s" %
                        header_value)
                }
            ]
        }
        return self.render_to_response(context)

    def plan_is_running(self, item_path=None):
        context = {
            "_links": {
                "self": {"href": self.full_url(cherrypy.request.path_info)}
            },
            "messages": [
                {
                    "_links": {
                        "self": {
                            "href": self.full_url(cherrypy.request.path_info)
                        }
                    },
                    "type": constants.INVALID_REQUEST_ERROR,
                    "message": (
                        "Operation not allowed while plan is running/stopping")
                }
            ]
        }
        return self.render_to_response(context)

    def model_is_locked(self, item_path=None):
        context = {
            "_links": {
                "self": {"href": self.full_url(cherrypy.request.path_info)}
            },
            "messages": [
                {
                    "_links": {
                        "self": {
                            "href": self.full_url(cherrypy.request.path_info)
                        }
                    },
                    "type": constants.INVALID_REQUEST_ERROR,
                    "message": (
                        "Operation not allowed while the model is being "
                        "loaded from XML or restored")
                }
            ]
        }
        return self.render_to_response(context)

    def cannot_create_plan(self):
        msg, err_type = self._get_cannot_create_plan_errs()
        context = {
            "_links": {
                "self": {"href": self.full_url(cherrypy.request.path_info)}
            },
            "messages": [
                {
                    "type": err_type,
                    "message": (msg)
                }
            ]
        }
        return self.render_to_response(context)

    def _get_cannot_create_plan_errs(self):
        # assumes that the plan cannot be created for some reason,
        # that check should be performed before calling this method
        msg, err_type = '', constants.INVALID_REQUEST_ERROR
        if not self.execution_manager.plan_exists():
            msg += "Plan creation already in progress"
        elif not self.execution_manager.can_create_plan():
            if self.execution_manager.is_plan_running():
                msg += "Plan already running"
            elif self.execution_manager.is_plan_stopping():
                msg += "Previous plan is still stopping"
        return msg, err_type

    def render_to_response(self, context, template_name="default.json",
                           status=None):
        template = self.loader.get_template(template_name)
        if status is None:
            messages = context.get('messages', [])
            status = self.get_status_from_messages(messages)
        cherrypy.response.headers["Content-Type"] = "application/json"
        cherrypy.response.status = status
        return template.render({"context": context})

    def get_status_from_messages(self, messages, status=constants.OK):
        """
        Return a status code from error messages.
        """
        def get_error_status_code(error_type):
            return error_type, constants.ERROR_STATUS_CODES[error_type]

        if messages:
            error_codes = [
                get_error_status_code(err["type"]) for err in messages
            ]
            status_code = max(error_codes, key=itemgetter(1))[0]
            status = constants.ERROR_STATUS_CODES[status_code]
        return status

    def normalise_path(self, path):
        if not path:
            path = '/'
        if path != "/":
            path = path.rstrip("/")
        if not path.startswith("/"):
            path = "/" + path
        return path

    def _prepare_links(self, item):
        links = {
            "self": {"href": self.full_url(item.get_vpath())}
        }

        if isinstance(item, CollectionItem):
            links["collection-of"] = {"href": self.full_url(
                            "/item-types/%s" % item.item_type_id)}

        elif isinstance(item, RefCollectionItem):
            links["ref-collection-of"] = {"href": self.full_url(
                            "/item-types/%s" % item.item_type_id)}
        else:
            links["item-type"] = {"href": self.full_url(
                        "/item-types/%s" % item.item_type_id)}
        if item.source_vpath:
            links["inherited-from"] = {"href": self.full_url(
                item.source_vpath)}

        return links

    def _prepare_item_type_prefix(self, item, links_context):
        if item.source_vpath:
            prefix = 'reference-to-'
        else:
            current_keys = set(links_context.keys())
            default_keys = set(("self", "item-type"))
            try:
                prefix = current_keys.difference(default_keys).pop()
                prefix += '-'
            except KeyError:
                prefix = ''
        return prefix

    def _get_item_type(self, item):
        if item.is_collection() and item.source_vpath:
            return 'collection-of-%s' % item.item_type_id
        else:
            return item.item_type_id

    def generate_hal_context(self, item, children=None):
        links = self._prepare_links(item)
        prefix = self._prepare_item_type_prefix(item, links)

        context = {
            "id": item.item_id,
            "item-type-name": prefix + self._get_item_type(item),
            "_links": links
        }

        if children:
            embedded_items = []
            for child in children:
                embedded_items.append(self.generate_hal_context(child))
            context["_embedded"] = {"item": embedded_items}

        #ad hoc list of displayable key value pairs
        if hasattr(item, "get_state") and item.get_state():
            context["state"] = item.get_state()
        if hasattr(item, "applied_properties_determinable"):
            context["applied_properties_determinable"] = \
                item.applied_properties_determinable
        if hasattr(item, "properties"):
            merged_props = item.get_merged_properties(skip_views=True)
            if merged_props:
                context["properties"] = merged_props
                if item.source_vpath:
                    overwritten_props = item.get_properties(
                        skip_views=True).keys()
                    if overwritten_props:
                        context["properties-overwritten"] = overwritten_props
        if item.item_type_id == "root":
            context["version"] = get_litp_version()
            context["litp-packages"] = get_litp_packages()

        return context

    def _decode(self, request_method):
        operations = {
            "POST": "Create",
            "PUT": "Update",
            "GET": "Retrieve",
            "DELETE": "Remove"
         }
        return operations.get(request_method, "Unsupported")

    def get_internal_resource(self, method, *method_args, **method_kwargs):
        request_method = cherrypy.request.method
        cherrypy.request.method = 'GET'
        result = method(*method_args, **method_kwargs)
        cherrypy.request.method = request_method
        return result

    def _get_item_from_model_snapshot(self, item_path):
        item_path = self.normalise_path(item_path)
        # No.
        #items_snapshot = dict(self.model_manager.items)
        #return items_snapshot.get(item_path)
        return self.model_manager.get_item(item_path)

    def _parse_recurse_depth(self, recurse_depth):
        try:
            if recurse_depth is not None:
                return int(recurse_depth)
            else:
                return 1
        except ValueError:
            return ValidationError(
                item_path=cherrypy.request.path_info,
                error_message="Invalid value for recurse_depth",
                error_type=constants.INVALID_REQUEST_ERROR)
