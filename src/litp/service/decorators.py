import cherrypy
from litp.service.controllers.mixins import LitpControllerMixin

SUPPORTED_CONTENT_TYPES = [
    'application/json',
    'application/xml'
]


def request_method_allowed(request_method_list,
                           fallback_method_name='method_not_allowed'):
    def wrapped(method):
        def wrapper(self, *args, **kwargs):
            content_type = cherrypy.request.headers.get('Content-Type')
            request_method = cherrypy.request.method
            path_info = cherrypy.request.path_info
            if not path_info.startswith('/puppet_'):
                if request_method in ['PUT', 'POST']:
                    if content_type not in SUPPORTED_CONTENT_TYPES:
                        return self.invalid_header()

            if cherrypy.request.method in request_method_list:
                return method(self, *args, **kwargs)
            else:
                return getattr(self, fallback_method_name)()
        return wrapper
    return wrapped


def check_plan_not_running(func):
    def call_request(*args, **kwargs):
        exec_mngr = cherrypy.config["execution_manager"]
        if exec_mngr.is_plan_running() or exec_mngr.is_plan_stopping():
            return LitpControllerMixin().plan_is_running()
        else:
            return func(*args, **kwargs)

    return call_request


def check_cannot_create_plan(func):
    def call_request(*args, **kwargs):
        exec_mngr = cherrypy.config["execution_manager"]
        if exec_mngr.can_create_plan():
            return func(*args, **kwargs)
        else:
            return LitpControllerMixin().cannot_create_plan()
    return call_request
