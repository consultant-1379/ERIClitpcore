import cherrypy
import json
import unittest

from litp.core import constants
from litp.core.model_manager import ModelManager
from litp.service.controllers import PropertyTypeController
from litp.core.model_type import PropertyType

from base import Mock


class TestPropertyTypeController(unittest.TestCase):

    def setUp(self):
        self.prop_type_controller = PropertyTypeController()
        self.swp = cherrypy.request
        cherrypy.request = Mock()
        cherrypy.request.path_info = ''
        cherrypy.request.method = 'GET'
        cherrypy.request.headers = {}
        cherrypy.request.base = ''
        cherrypy.request.script_name = ''
        model_manager = ModelManager()
        model_manager.register_property_type(PropertyType("basic_string"))

        cherrypy.config = {'model_manager': model_manager}

    def tearDown(self):
        cherrypy.request = self.swp

    def test_list_property_types(self):
        cherrypy.request.path_info = '/property-types'
        response = json.loads(self.prop_type_controller.list_property_types())
        self.assertEqual(
            response['_links']['self']['href'], '/property-types/')
        self.assertEqual(response['_embedded']['property-type'][0]['id'],
                         'basic_string')
        self.assertEqual(
            response['_embedded']['property-type'][0]['regex'], '^.*$')
        self.assertEqual(
            response['_embedded']['property-type'][0]['_links']['self']['href'],
            '/property-types/basic_string')

    def test_get_property_type_invalid_id(self):
        property_type_id = 'some_id'
        cherrypy.request.path_info = '/property-types/%s' % property_type_id
        response = json.loads(
            self.prop_type_controller.get_property_type(property_type_id)
        )
        self.assertTrue('data' not in response)
        self.assertTrue('messages' in response)
        self.assertEquals(len(response['messages']), 1)
        err = response['messages'][0]
        self.assertEquals(err['message'], 'Not found')
        self.assertEquals(
            err['_links']['self']['href'], cherrypy.request.path_info)
        self.assertEquals(err['type'], constants.INVALID_LOCATION_ERROR)

    def test_get_property_type_valid_id(self):
        property_type_id = 'basic_string'
        cherrypy.request.path_info = '/property-types/%s' % property_type_id
        response = json.loads(
            self.prop_type_controller.get_property_type(property_type_id)
        )

        self.assertEqual(response['regex'], '^.*$')
        self.assertEqual(response['_links']['self']['href'],
                         '/property-types/basic_string')
        self.assertEqual(response['id'], 'basic_string')
