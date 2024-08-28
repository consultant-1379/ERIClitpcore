import cherrypy
import json
import unittest

from litp.core import constants
from litp.service.controllers import LitpControllerMixin
from litp.service.utils import human_readable_request_type
from base import Mock


class TestLitpControllerMixin(unittest.TestCase):

    def setUp(self):
        self.litp_mixin = LitpControllerMixin()

    def test_render_to_response(self):
        context = {'content': 'some awesome content'}
        response = self.litp_mixin.render_to_response(context)
        self.assertEqual(response, json.dumps(context))
        self.assertEqual(cherrypy.response.status, 200)
        self.assert_("Content-Type" in cherrypy.response.headers)
        self.assertEqual(
            cherrypy.response.headers.get("Content-Type"), 'application/json'
        )

    def test_get_status_no_messages(self):
        messages = []
        status = self.litp_mixin.get_status_from_messages(messages)
        self.assertEqual(status, constants.OK)

    def test_get_status_single_message(self):
        messages = [{'type': constants.INVALID_LOCATION_ERROR}]
        status = self.litp_mixin.get_status_from_messages(messages)
        self.assertEqual(status, constants.NOT_FOUND)

    def test_get_status_multiple_messages(self):
        messages = [
            {'type': constants.INVALID_LOCATION_ERROR},
            {'type': constants.INVALID_CHILD_TYPE_ERROR}
        ]
        status = self.litp_mixin.get_status_from_messages(messages)
        self.assertEqual(status, constants.UNPROCESSABLE)

    def test_normalise_path(self):
        path = self.litp_mixin.normalise_path(path=None)
        self.assertEqual(path, '/')

        path = self.litp_mixin.normalise_path(path='/')
        self.assertEqual(path, '/')

        path = self.litp_mixin.normalise_path(path='/some_path')
        self.assertEqual(path, '/some_path')

        path = self.litp_mixin.normalise_path(path='/some_path/')
        self.assertEqual(path, '/some_path')

    def test_full_url(self):
        swp = cherrypy.request.base
        cherrypy.request.base = '/my/path/info'
        path = self.litp_mixin.full_url(rel_path='/my/path/info/item')
        self.assertEqual(path, '/my/path/info/item')

        path = self.litp_mixin.full_url(rel_path='/item')
        self.assertEqual(path, '/my/path/info/item')
        cherrypy.request.base = swp

    def test_method_not_allowed(self):
        response = json.loads(self.litp_mixin.method_not_allowed())
        self.assertTrue('messages' in response)
        self.assertTrue(isinstance(response['messages'], list))
        self.assertEqual(len(response['messages']), 1)
        err = response['messages'][0]
        self.assertEquals(
            err['message'],
            '%s method on path not allowed'
            % human_readable_request_type(cherrypy.request.method)
        )
        self.assertEqual(err['type'], constants.METHOD_NOT_ALLOWED_ERROR)
        self.assertEqual(cherrypy.response.status, 405)

    def test_invalid_header(self):
        swp = cherrypy.request
        cherrypy.request = Mock()
        cherrypy.request.path_info = ''
        cherrypy.request.base = ''
        cherrypy.request.script_name = ''
        cherrypy.request.method = 'POST'
        cherrypy.request.headers = {}
        cherrypy.request.headers['Content-Type'] = 'application/json'
        response = json.loads(self.litp_mixin.invalid_header())
        self.assertTrue('messages' in response)
        self.assertTrue(isinstance(response['messages'], list))
        self.assertEqual(len(response['messages']), 1)
        err = response['messages'][0]
        self.assertEquals(
            err['message'],
            "Invalid 'Content-Type' header value: application/json")
        self.assertEqual(err['_links']['self']['href'], '')
        self.assertEqual(err['type'], constants.HEADER_NOT_ACCEPTABLE_ERROR)
        self.assertEqual(cherrypy.response.status, 406)
        cherrypy.request = swp

    def test_invalid_header_absent(self):
        swp = cherrypy.request
        cherrypy.request = Mock()
        cherrypy.request.path_info = ''
        cherrypy.request.base = ''
        cherrypy.request.script_name = ''
        cherrypy.request.method = 'POST'
        cherrypy.request.headers = {}
        response = json.loads(self.litp_mixin.invalid_header())
        self.assertTrue('messages' in response)
        self.assertTrue(isinstance(response['messages'], list))
        self.assertEqual(len(response['messages']), 1)
        err = response['messages'][0]
        self.assertEquals(
            err['message'],
            "Invalid 'Content-Type' header value: None")
        self.assertEqual(err['_links']['self']['href'], '')
        self.assertEqual(err['type'], constants.HEADER_NOT_ACCEPTABLE_ERROR)
        self.assertEqual(cherrypy.response.status, 406)
        cherrypy.request = swp

    def test_parse_recurse_depth_valid(self):
        response = self.litp_mixin._parse_recurse_depth(5)
        self.assertEqual(5, response)

    def test_parse_recurse_depth_invalid(self):
        response = self.litp_mixin._parse_recurse_depth('Nowt')
        self.assertEquals(
            response.error_message,
            "Invalid value for recurse_depth")
        self.assertEqual(response.item_path, '/')
        self.assertEqual(response.error_type, constants.INVALID_REQUEST_ERROR)

    def test_parse_recurse_depth_absent(self):
        response = self.litp_mixin._parse_recurse_depth(None)
        self.assertEqual(1, response)
