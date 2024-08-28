##############################################################################
# COPYRIGHT Ericsson 2013
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################

import cherrypy
import mimetypes
import grp
import pam
import pwd
import stat
import struct
import socket
import hashlib
import os
import re


from collections import namedtuple
from datetime import datetime, timedelta

from cherrypy._cperror import _HTTPErrorTemplate
from cherrypy.process.plugins import Daemonizer, PIDFile

from litp.core.scope_utils import setup_threadlocal_scope
from litp.core.scope_utils import cleanup_threadlocal_scope
from litp.core.litp_logging import LitpLogger
from litp.core.litp_threadpool import shutdown
from litp.service.dispatcher import TrailingSlashRoutesDispatcher
from litp.service import controllers
from litp.service.utils import get_db_availability


def secureheaders():
    headers = cherrypy.response.headers

    if (cherrypy.server.ssl_certificate != None and
        cherrypy.server.ssl_private_key != None):
        headers['Strict-Transport-Security'] = 'max-age=31536000'  # one year


cherrypy.tools.secureheaders = cherrypy.Tool('before_finalize',
secureheaders, priority=60)


def error_page(status, message, traceback, version):
    data = {'status': status,
            'message': message,
            'traceback': ''}
    return re.sub(r'(\n\s*<span>)(Powered by).*(</span>\s*\n)',
                  r'\1<!--\2 a webserver-->\3',
                  _HTTPErrorTemplate) % data

LITP_REST_V1 = "/litp/rest/v1"
PUPPET_CALLBACK = "/execution"
XML_PATH = "/litp/xml"
UPGRADE_PATH = "/litp/upgrade"

logger = LitpLogger()


def litp_rest_v1_routes():
    dispatcher = TrailingSlashRoutesDispatcher(mount_point=LITP_REST_V1)

    dispatcher.connect(
        name='plans', route='/plans/',
        controller=controllers.PlanController(),
        action='list_plans', conditions=dict(method=['GET']))

    dispatcher.connect(
        name='plans', route='/plans/',
        controller=controllers.PlanController(),
        action='create_plan', conditions=dict(method=['POST']))

    dispatcher.connect(
        name='plans', route='/plans/',
        controller=controllers.PlanController(),
        action='create_reboot_plan', conditions=dict(method=['POST']))

    dispatcher.connect(
        name='plan', route='/plans/{plan_id}/',
        controller=controllers.PlanController(),
        action='get_plan', conditions=dict(method=['GET']))

    dispatcher.connect(
        name='update_plan', route='/plans/{plan_id}/',
        controller=controllers.PlanController(),
        action='update_plan', conditions=dict(method=['PUT']))

    dispatcher.connect(
        name='delete_plan', route='/plans/{plan_id}/',
        controller=controllers.PlanController(),
        action='delete_plan', conditions=dict(method=['DELETE']))

    dispatcher.connect(
        name='phases', route='/plans/{plan_id}/phases/',
        controller=controllers.PlanController(),
        action='list_phases', conditions=dict(method=['GET']))

    dispatcher.connect(
        name='phase',
        route=r'/plans/{plan_id}/phases/{phase_id:\d+}/',
        controller=controllers.PlanController(),
        action='get_phase', conditions=dict(method=['GET']))

    dispatcher.connect(
        name='tasks',
        route=r'/plans/{plan_id}/phases/{phase_id:\d+}/tasks/',
        controller=controllers.PlanController(),
        action='list_tasks', conditions=dict(method=['GET']))

    dispatcher.connect(
        name='task',
        route=r'/plans/{plan_id}/phases/{phase_id:\d+}/tasks/{task_id}/',
        controller=controllers.PlanController(),
        action='get_task', conditions=dict(method=['GET']))

    dispatcher.connect(
        name='litp_get', route='/litp/',
        controller=controllers.LitpServiceController(),
        action='list_services', conditions=dict(method=['GET']))

    dispatcher.connect(
        name='litp_post_put_delete', route='/litp/',
        controller=controllers.MiscController(),
        action='method_not_allowed_blank',
        conditions=dict(method=["POST", "PUT", "DELETE"]))

    dispatcher.connect(
        name='litp_get', route='/litp/{service_id}/',
        controller=controllers.LitpServiceController(),
        action='get_service', conditions=dict(method=["GET"]))

    dispatcher.connect(
        name='logging_put', route='/litp/logging/',
        controller=controllers.LitpServiceController(),
        action='update_service_while_plan_running',
        conditions=dict(method=["PUT"]))

    dispatcher.connect(
        name='maintenance_put', route='/litp/maintenance/',
        controller=controllers.LitpServiceController(),
        action='update_service_while_plan_running',
        conditions=dict(method=["PUT"]))

    dispatcher.connect(
        name='litp_put', route='/litp/{service_id}/',
        controller=controllers.LitpServiceController(),
        action='update_service', conditions=dict(method=["PUT"]))

    dispatcher.connect(
        name='litp_post_delete', route='/litp/{item_path}/',
        controller=controllers.LitpServiceController(),
        action='method_not_allowed',
        conditions=dict(method=["POST", "DELETE"]))

    dispatcher.connect(
        name='item_types', route='/item-types/',
        controller=controllers.ItemTypeController(),
        action='list_item_types')

    dispatcher.connect(
        name='item_type', route='/item-types/{item_type_id}/',
        controller=controllers.ItemTypeController(),
        action='get_item_type')

    dispatcher.connect(
        name='property_types', route='/property-types/',
        controller=controllers.PropertyTypeController(),
        action='list_property_types')

    dispatcher.connect(
        name='property_type',
        route='/property-types/{property_type_id}/',
        controller=controllers.PropertyTypeController(),
        action='get_property_type')

    dispatcher.connect(
        name="item", route='{item_path:.*?}',
        controller=controllers.ItemController(),
        action='get_item', conditions=dict(method=['GET']))

    dispatcher.connect(
        name="create_snapshot",
        route='/snapshots/{snapshot_name:.*?}/',
        controller=controllers.SnapshotController(),
        action="create_snapshot",
        conditions={"method": ["POST"]}
        )

    dispatcher.connect(
        name="delete_snapshot",
        route=r'/snapshots/{snapshot_name}/',
        controller=controllers.SnapshotController(),
        action="delete_snapshot",
        conditions={"method": ["DELETE"]}
        )

    dispatcher.connect(
        name="restore_or_remove_snapshot",
        route='/snapshots/{snapshot_name}/',
        controller=controllers.SnapshotController(),
        action="restore_or_remove_snapshot",
        conditions={"method": ["PUT"]}
        )

    dispatcher.connect(
        name="packages_import",
        route='/import/',
        controller=controllers.PackagesImportController(),
        action="handle_import",
        conditions={"method": ["PUT"]}
    )

    dispatcher.connect(
        name=None,
        route='{item_path:^/litp.*|^/item-types.*'
            '|^/property-types.*|/?plans/plan/.*}',
        controller=controllers.ItemController(),
        action='method_not_allowed',
        conditions=dict(method=["POST", "PUT", "DELETE"]))

    dispatcher.connect(
        name="create_json_item",
        route='{item_path:.*?}',
        controller=controllers.ItemController(),
        action='create_json_item',
        conditions={"method": ["POST"], "function": cb_is_json_content_type})

    dispatcher.connect(
        name="update_item", route='{item_path:.*?}',
        controller=controllers.ItemController(),
        action='update_item',
        conditions={"method": ["PUT"], "function": cb_is_json_content_type})

    dispatcher.connect(
        name="delete_item", route='{item_path:.*?}',
        controller=controllers.ItemController(),
        action='delete_item',
        conditions={"method": ["DELETE"]})

    dispatcher.connect(
        name="create_item", route='{item_path:.*?}',
        controller=controllers.ItemController(),
        action='invalid_header',
        conditions={
            "method": ["POST", "PUT", "DELETE"]
        })

    dispatcher.connect(
        name='method_not_supported', route='{item_path:.*?}',
        controller=controllers.MiscController(),
        action='method_not_allowed',
        conditions={'function': cb_method_not_supported})

    dispatcher.connect(
        name="default_route", route='{path_info:.*?}',
        controller=controllers.MiscController(),
        action='default_route')

    return dispatcher


def xml_routes():
    dispatcher = TrailingSlashRoutesDispatcher(mount_point=XML_PATH)

    dispatcher.connect(
        name="export_xml_item", route='{item_path:.*?}',
        controller=controllers.XmlController(),
        action='export_xml_item',
        conditions={"method": "GET"})

    dispatcher.connect(
        name="import_xml_item", route='{item_path:.*?}',
        controller=controllers.XmlController(),
        action='import_xml_item',
        conditions={"method": ["POST"], "function": cb_is_xml_content_type})

    return dispatcher


def upgrade_routes():
    dispatcher = TrailingSlashRoutesDispatcher(mount_point=UPGRADE_PATH)

    dispatcher.connect(
        name="upgrade", route='{item_path:.*?}',
        controller=controllers.UpgradeController(),
        action='upgrade',
        conditions={"method": ["POST"]})

    return dispatcher


def cb_is_json_content_type(environ, result):
    return environ.get("CONTENT_TYPE") == "application/json"


def cb_is_xml_content_type(environ, result):
    return environ.get("CONTENT_TYPE") == "application/xml"


def cb_method_not_supported(environ, result):
    supported_methods = ['GET', 'POST', 'PUT', 'DELETE']
    return environ['REQUEST_METHOD'] not in supported_methods


class CherrypyServer(object):

    POSITIVE_TIME_DELTA = 60
    NEGATIVE_TIME_DELTA = 5

    def __init__(self):
        self.logged_users = {}
        self.allowed_socket_groups = set()
        self._setup_routes()
        self.login = None
        self.pid_file_path = '/var/run/litp_service.py.pid'

    def _setup_routes(self):

        global_config = {
            'request.error_response': self.handle_error,
            'request.show_tracebacks': False,
            'request.error_page': {"default": error_page},
            'tools.secureheaders.on': True
        }

        cherrypy.config.update(global_config)

        basic_authentication_conf = {
            'tools.auth_basic.on': True,
            'tools.auth_basic.realm': 'earth',
            'tools.auth_basic.checkpassword': self.cb_checkpassword
        }

        litp_rest_v1_dispatcher = litp_rest_v1_routes()
        litp_rest_v1_conf = {
            'request.dispatch': litp_rest_v1_dispatcher,
            'response.timeout': 7200,
            'request.error_response': self.handle_litp_error
        }
        litp_rest_v1_conf.update(basic_authentication_conf)

        xml_dispatcher = xml_routes()
        xml_conf = {
            'request.dispatch': xml_dispatcher,
            'response.timeout': 3600
        }
        xml_conf.update(basic_authentication_conf)

        upgrade_dispatcher = upgrade_routes()
        upgrade_conf = {
            'request.dispatch': upgrade_dispatcher
        }
        upgrade_conf.update(basic_authentication_conf)

        cherrypy.tree.mount(
            None, LITP_REST_V1, config={"/": litp_rest_v1_conf})
        cherrypy.tree.mount(
            None, XML_PATH, config={"/": xml_conf})
        cherrypy.tree.mount(
            None, UPGRADE_PATH, config={"/": upgrade_conf})

        cherrypy.tree.mount(None, "/")

    def start(self, daemonize=False):
        """Starts litpd service.

           Normal Start procedure is to fork a daemon before mounting
           content root.
        """
        logger.event.debug("Starting litpd service")
        cherrypy.engine.signal_handler.handlers = {
            'SIGTERM': self.cb_sighandler,
            'SIGHUP': self.cb_sighandler,
            'SIGINT': self.cb_sighandler,
        }
        cherrypy.engine.signal_handler.subscribe()

        # This will be used by CherryPy's serve_file() function.
        mimetypes.add_type('application/xml', '.xsd')

        socket_server = self._setup_unix_socket()

        try:
            if daemonize:
                logger.trace.debug("Daemonizing service")
                litp_daemon = Daemonizer(cherrypy.engine)
                litp_daemon.subscribe()
                PIDFile(
                    cherrypy.engine, self.pid_file_path
                ).subscribe()

            logger.event.debug("Starting cherrypy service")

            cherrypy.engine.start()

            logger.set_log_name("LITP Daemon")
            logger.event.info("litpd service started")
            if daemonize:
                try:
                    os.chmod(self.pid_file_path, 0644)
                except OSError as e:
                    logger.trace.exception(e)
                    raise e

            if socket_server:
                self._setup_socket_perms(socket_server.socket_file)

            cherrypy.engine.block()
        except:  # pylint: disable=W0702
            logger.trace.exception("Exception running daemon")

    def _setup_unix_socket(self):
        socket_file = cherrypy.config.get('litp_socket_file')
        socket_file_ok = False
        if socket_file:
            if os.path.exists(socket_file):
                mode = os.stat(socket_file).st_mode
                socket_file_ok = stat.S_ISSOCK(mode)
                if not socket_file_ok:
                    if stat.S_ISDIR(mode):
                        logger.trace.error("'litp_socket_file'"
                                           " in litpd.conf cannot point"
                                           " to a directory")
                    else:
                        logger.trace.error("'litp_socket_file'"
                                           " in litpd.conf cannot point"
                                           " to an existing file")
                    return None
            elif not os.path.exists(os.path.dirname(socket_file)):
                logger.trace.error("'litp_socket_file' in litpd.conf"
                                   " points to a nonexisting directory")
            else:
                socket_file_ok = True

        socket_server = None
        if socket_file and socket_file_ok:
            socket_server = cherrypy._cpserver.Server()
            socket_server.socket_file = socket_file
            socket_server.subscribe()
        return socket_server

    def _setup_socket_perms(self, socket_file):
        socket_group = cherrypy.config.get('litp_socket_file_group')
        allowed_groups = cherrypy.config.get('litp_socket_allowed_groups',
                                             '').split(',')
        logger.trace.debug('allowed_groups: %s', allowed_groups)
        for g in allowed_groups:
            try:
                gid = grp.getgrnam(g).gr_gid
                self.allowed_socket_groups.add(gid)
            except KeyError:
                logger.trace.error("Groups in 'litp_socket_allowed_users'"
                                   " does not exist: %s", g)
        try:
            gid = grp.getgrnam(socket_group).gr_gid
        except KeyError:
            socket_group = None
            logger.trace.error("Group in 'litp_socket_file_group'"
                               " does not exist: %s", socket_group)
        if socket_group:
            os.chmod(socket_file, 0660)
            os.chown(socket_file, -1, gid)

    def _before_request(self):
        setup_threadlocal_scope()

    def _before_finalize(self):
        cleanup_threadlocal_scope()

    def cb_sighandler(self):
        logger.event.info("Got shutdown signal")
        cherrypy.engine.stop()

        setup_threadlocal_scope()
        try:
            cherrypy.config["execution_manager"].kill_plan()
        finally:
            cleanup_threadlocal_scope()
        logger.trace.debug("Engine stopped")
        shutdown()
        cherrypy.engine.exit()
        cherrypy.config["db_storage"].close()
        logger.trace.debug("Shutdown complete")

    def _check_uid_in_group(self, uid, request_username):
        try:
            user_data = pwd.getpwuid(uid)
            username = user_data.pw_name
            user_gid = user_data.pw_gid
        except KeyError:
            return False
        if username != request_username:
            logger.trace.error("Request username %s"
                               " does not match uid of request",
                               request_username)
            return False
        if not self.allowed_socket_groups:
            return True
        for g in self.allowed_socket_groups:
            if username in grp.getgrgid(g).gr_mem:
                return True
            if user_gid == g:
                return True
        return False

    def cb_checkpassword(self, realm, username, password):
        """
        logged_users contains a list of users that were able to authenticate
        successfully, along with their ip and the expiration of that session.
        """
        sock_info = self._get_sockopt()
        if sock_info.family == socket.AF_INET:
            key = self._generate_auth_id(username, password)
            if not self.logged_users.get(key) or self._session_expired(key):
                login_ok = self._authenticate_user(username, password)
            else:
                login_ok = self.logged_users[key].access_granted
        elif sock_info.family == socket.AF_UNIX:
            login_ok = self._check_uid_in_group(sock_info.uid, username)
        return login_ok

    def _get_request_ip(self):
        return cherrypy.request.remote.ip

    def _get_sockopt(self):
        s = cherrypy.request.rfile.rfile._sock
        creds = s.getsockopt(socket.SOL_SOCKET,
                             socket.SO_PEERCRED,
                             struct.calcsize("3i"))
        pid, uid, gid = struct.unpack("3i", creds)
        SockInfo = namedtuple('SockInfo', ['uid', 'family', 'proto'])
        return SockInfo(uid, s.family, s.proto)

    def _generate_auth_id(self, username, password):
        key = "{0}_{1}_{2}".format(username, self._get_request_ip(), password)
        return hashlib.md5(key).hexdigest()

    def _authenticate_user(self, username, password):
        key = self._generate_auth_id(username, password)
        login_ok = pam.authenticate(username, password)
        if login_ok:
            self._create_positive_logged_users_entry(key)
        else:
            self._create_negative_logged_users_entry(key)
        return login_ok

    def _session_expired(self, key):
        tiniest_token = AuthorizationToken(datetime.min, False)
        return datetime.now() > self.logged_users.get(key,
                                                      tiniest_token).expiration

    def _create_positive_logged_users_entry(self, key):
        """ Creates an entry that grants access to that user """
        date = datetime.now() + timedelta(seconds=self.POSITIVE_TIME_DELTA)
        self.logged_users[key] = AuthorizationToken(date, True)

    def _create_negative_logged_users_entry(self, key):
        """ Creates an entry that denies access to that user """
        date = datetime.now() + timedelta(seconds=self.NEGATIVE_TIME_DELTA)
        self.logged_users[key] = AuthorizationToken(date, False)

    def handle_error(self):
        exp_msg = "Exception in call: %s" % (cherrypy.request.path_info,)
        logger.trace.exception(exp_msg + " with params %s",
                               cherrypy.request.query_string)
        raise

    def handle_litp_error(self):
        exp_msg = "Exception in call: %s" % (cherrypy.request.path_info,)
        logger.trace.exception(exp_msg + " with params %s",
                               cherrypy.request.query_string)

        my_path = ''.join([
            (cherrypy.request.base
                if cherrypy.request.base else ''),
            (cherrypy.request.script_name
                if cherrypy.request.script_name else ''),
            (cherrypy.request.path_info
                if cherrypy.request.path_info else '')])

        cherrypy.response.headers["Content-Type"] = "application/json"

        if not get_db_availability():
            cherrypy.response.status = 503
            cherrypy.response.body = """
            {
                "_links": {
                    "self": {
                        "href": "%s"
                    }
                },
                "messages": [
                    {
                        "_links": {
                            "self": {
                                "href": "%s"
                            }
                        },
                        "message": "A dependent service is unavailable",
                        "type": "ServerUnavailableError"
                    }
                ]
            }
            """ % (my_path, my_path)
            return

        if cherrypy.response.status != 500:
            cherrypy.response.status = 500
            cherrypy.response.body = """
            {
                "_links": {
                    "self": {
                        "href": "%s"
                    }
                },
                "messages": [
                    {
                        "type": "InternalServerError",
                        "message": "An exception occurred while \
accessing this item.",
                        "_links": {
                            "self": {
                                "href": "%s"
                            }
                        }
                    }
                ]
            }
            """ % (my_path, my_path)


class AuthorizationToken(object):
    """
    Very simple class to identify an authorization token, either
    positive or negative. It just contains its expiration time and
    whether it grants access or not. If we used Python 2.7 this should
    be done via a NamedTuple
    """
    def __init__(self, expiration, access_granted):
        self.expiration = expiration
        self.access_granted = access_granted
