import unittest
import cherrypy
import pam
import hashlib
from mock import patch, Mock

from datetime import datetime, timedelta

from litp.core.model_manager import ModelManager
from litp.service.cherrypy_server import CherrypyServer
from litp.service.cherrypy_server import AuthorizationToken
from base import MethodCallLogger

URL_BASE = "http://localhost:9999"
URL_BASE_PATH = "/litp/rest/v1"


class CherrypyServerTest(unittest.TestCase):
    def setUp(self):
        self.model_manager = ModelManager()

        cherrypy.config.update({
            'model_manager': self.model_manager
        })

        self.server = CherrypyServer()

    def test__before_request_GET(self):
        pass

    def test__before_request_not_GET(self):
        cherrypy.request.method = "POST"
        pass

    def test__create_positive_logged_users_entry(self):
        key = 'my_key'
        self.server._create_positive_logged_users_entry(key)
        self.assertTrue(key in self.server.logged_users)
        auth_token = self.server.logged_users[key]
        self.assertTrue(isinstance(auth_token, AuthorizationToken))
        self.assertTrue(auth_token.access_granted)
        self.assertTrue(isinstance(auth_token.expiration, datetime))

    def test__create_negative_logged_users_entry(self):
        key = 'my_key'
        self.server._create_negative_logged_users_entry(key)
        self.assertTrue(key in self.server.logged_users)
        auth_token = self.server.logged_users[key]
        self.assertTrue(isinstance(auth_token, AuthorizationToken))
        self.assertFalse(auth_token.access_granted)
        self.assertTrue(isinstance(auth_token.expiration, datetime))

    def test__get_request_ip(self):
        swp = cherrypy.request.remote.ip
        my_ip = "1.2.3.4"
        cherrypy.request.remote.ip = my_ip
        self.assertEquals(self.server._get_request_ip(), my_ip)
        cherrypy.request.remote.ip = swp

    def test__session_expired(self):
        key = 'my_key'
        self.server._create_positive_logged_users_entry(key)
        self.assertFalse(self.server._session_expired(key))

        auth_token = self.server.logged_users[key]
        auth_token.expiration -= timedelta(
            seconds=self.server.POSITIVE_TIME_DELTA)
        self.assertTrue(self.server._session_expired(key))

        self.server._create_negative_logged_users_entry(key)
        self.assertFalse(self.server._session_expired(key))

        auth_token = self.server.logged_users[key]
        auth_token.expiration -= timedelta(
            seconds=self.server.NEGATIVE_TIME_DELTA)
        self.assertTrue(self.server._session_expired(key))

    def test__session_expired_no_user(self):
        self.assertTrue(self.server._session_expired(None))

    def test__authenticate_user(self):
        self.server._create_positive_logged_users_entry = MethodCallLogger(
            self.server._create_positive_logged_users_entry
        )

        self.server._create_negative_logged_users_entry = MethodCallLogger(
            self.server._create_negative_logged_users_entry
        )

        with patch('pam.authenticate', return_value=False) as mock_pam:
            with patch('litp.service.cherrypy_server'
                            '.CherrypyServer._get_sockopt') as mock_sockopt:
                username = "user"
                password = "pass"
                mock_sockopt.return_value = Mock(uid=0,family=2,proto=6)
                self.server._authenticate_user(username, password)
                self.assertTrue(
                    self.server._create_negative_logged_users_entry.was_called)
                self.assertFalse(
                    self.server._create_positive_logged_users_entry.was_called)
                self.assertFalse(self.server.login)

                #reset method call logger flag for subsequent call
                self.server._create_positive_logged_users_entry.was_called = False
                self.server._create_negative_logged_users_entry.was_called = False

                pam.authenticate = lambda x, y: True
                self.server._authenticate_user(username, password)
                self.assertTrue(
                    self.server._create_positive_logged_users_entry.was_called)
                self.assertFalse(
                    self.server._create_negative_logged_users_entry.was_called)
                key = self.server._generate_auth_id(username, password)
                self.assertTrue(key in self.server.logged_users)

    def test_checkpassword(self):
        self.server._authenticate_user = MethodCallLogger(
            self.server._authenticate_user
        )
        try:
            swp_auth = pam.authenticate
            swp_ip = self.server._get_request_ip

            username = "user"
            password = "pass"
            self.server._get_request_ip = lambda: '1.2.3.4'
            pam.authenticate = lambda x, y: True

            with patch('litp.service.cherrypy_server'
                            '.CherrypyServer._get_sockopt') as mock_sockopt:
                mock_sockopt.return_value = Mock(uid=0,family=2,proto=6)
                res = self.server.cb_checkpassword("realm", username, password)

            self.assertTrue(self.server._authenticate_user.was_called)
            self.assertTrue(len(self.server.logged_users) == 1)
            self.assertTrue(res)

            #reset method call logger flag for subsequent call
            self.server._authenticate_user.was_called = False

            with patch('litp.service.cherrypy_server'
                            '.CherrypyServer._get_sockopt') as mock_sockopt:
                mock_sockopt.return_value = Mock(uid=0,family=2,proto=6)
                res = self.server.cb_checkpassword("realm", username, password)

            self.assertFalse(self.server._authenticate_user.was_called)
            self.assertTrue(len(self.server.logged_users) == 1)
            self.assertTrue(res)

            #reset method call logger flag for subsequent call
            self.server._authenticate_user.was_called = False

            auth_token = self.server.logged_users.values()[0]
            auth_token.expiration -= timedelta(
                seconds=self.server.POSITIVE_TIME_DELTA)

            with patch('litp.service.cherrypy_server'
                            '.CherrypyServer._get_sockopt') as mock_sockopt:
                mock_sockopt.return_value = Mock(uid=0,family=2,proto=6)
                res = self.server.cb_checkpassword("realm", username, password)

            self.assertTrue(self.server._authenticate_user.was_called)
            self.assertTrue(len(self.server.logged_users) == 1)
            self.assertTrue(res)
        finally:
            pam.authenticate = swp_auth
            self.server._get_request_ip = swp_ip

    def test_generate_auth_id(self):
        username = "user name"
        password = "pass word"
        ip = "123.123.123.123"
        key = "{0}_{1}_{2}".format(username, ip, password)
        hash_id = hashlib.md5(key).hexdigest()

        swp = self.server._get_request_ip
        self.server._get_request_ip = lambda: ip
        self.assertEqual(
            self.server._generate_auth_id(username, password), hash_id)
        self.server._get_request_ip = swp
