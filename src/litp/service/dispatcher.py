import cherrypy
from litp.service.utils import get_maintenance
from litp.core.litp_logging import LitpLogger
from litp.core.scope_utils import setup_threadlocal_scope
from litp.core.scope_utils import cleanup_threadlocal_scope
from functools import wraps

log = LitpLogger()


# TODO: Maybe use scope_utils.threadlocal_scope instead
def wrap_handler(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        setup_threadlocal_scope()
        try:
            return function(*args, **kwargs)
        finally:
            cleanup_threadlocal_scope()
    return wrapper


class TrailingSlashRoutesDispatcher(cherrypy.dispatch.RoutesDispatcher):

    def __init__(self, mount_point):
        super(TrailingSlashRoutesDispatcher, self).__init__()
        self.mount_point = mount_point

    def find_handler(self, path_info):
        if not path_info.endswith('/'):
            path_info += '/'
            request = cherrypy.serving.request
            if hasattr(request, 'wsgi_environ'):
                request.wsgi_environ['PATH_INFO'] = path_info
        handler = super(
            TrailingSlashRoutesDispatcher, self
        ).find_handler(path_info)
        if path_info == '//dummy.html/':
            # happens only on startup, according to cherrypy docs to
            # Check Application config for incorrect static paths.
            # at the moment, one request per app:
            # /litp/rest/v1
            # /litp/upgrade
            # /execution
            # /litp/xml
            # in this case we allow the request, as cherrypy needs it to start
            return handler
        if not self._handler_allows_maintenance(handler) and\
                                                    self._maintenance_on():
            return self.return_503
        return wrap_handler(handler)

    def return_503(self, *args, **kwargs):
        cherrypy.response.status = 503
        cherrypy.response.headers["Content-Type"] = "application/json"
        return '{"messages": [{"message"'\
               ': "LITP is in maintenance mode", "type": '\
               '"ServerUnavailableError"}]}'

    def _maintenance_on(self):
        return get_maintenance()

    def _handler_allows_maintenance(self, handler):
        '''
        handler is a method within a particular controller class, ie a
        reference to ItemController.get_item.
        In general we want the controllers to define an allows_maintenance
        method if they allow maintenance mode.
        A per-method granularity is also supported (see update_service in
        LitpServiceController)
        '''
        default_value = False
        if not handler:
            # no method at all
            return default_value
        # handler.__self__ is the object that instanced the handler method
        try:
            obj_instance = handler.__self__
        except AttributeError:
            # handler is not a method but a function. per-method exceptions
            # are not supported in that case
            obj_instance = None
        if hasattr(obj_instance, 'allows_maintenance_exceptions'):
            # that class has defined exceptions for allows_maintenance
            # check if handler is one of them
            if obj_instance.allows_maintenance_exceptions().get(handler):
                # method that decides if handler should allow maintenance mode
                return obj_instance.allows_maintenance_exceptions()[handler]()
        if not hasattr(handler, 'im_class'):
            # usually, classes implemented in C don't have this attribute.
            # Shouldn't be the case, as controllers inherit from object
            return default_value
        if not hasattr(handler.im_class, 'allows_maintenance'):
            # The base controller implements this method, so any controller
            # should contain this method.
            return default_value
        return handler.im_class.allows_maintenance()
