import cherrypy
import json
import unittest

from litp.core import constants
from litp.core.model_manager import ModelManager
from litp.service.controllers import ItemTypeController
from litp.core.model_type import ItemType, PropertyType, Property, Collection

from base import Mock


class TestItemTypeController(unittest.TestCase):

    def setUp(self):
        self.item_type_controller = ItemTypeController()
        self.swp = cherrypy.request
        cherrypy.request = Mock()
        cherrypy.request.path_info = ''
        cherrypy.request.method = 'GET'
        cherrypy.request.headers = {}
        cherrypy.request.base = ''
        cherrypy.request.script_name = ''
        model_manager = self._setup_model_manager()

        cherrypy.config = {'model_manager': model_manager}

    def tearDown(self):
        cherrypy.request = self.swp

    def _setup_model_manager(self):
        model_manager = ModelManager()
        model_manager.register_property_type(PropertyType("basic_string"))

        model_manager.register_item_type(
            ItemType("dummy", item_description="some description")
        )
        dummy_prop = Property('basic_string',
                           prop_description='A dummy property',
                           required=True)

        model_manager.register_item_type(ItemType(
                "collection",
                item_description="collection item."
        ))
        model_manager.register_item_type(
            ItemType('bigger_dummy',
                    item_description='More of a dummy item type',
                    extend_item='dummy',
                    dummy_property=dummy_prop,
                    collective=Collection('collection'))
        )
        return model_manager

    def test_list_item_types(self):
        response = json.loads(self.item_type_controller.list_item_types())

        self.assertEqual(response['_links']['self']['href'], '/item-types/')
        self.assertEqual(response['id'], 'item-types')
        self.assertEqual(
            response['_embedded']['item-type'][0]['_links']['self']['href'],
            '/item-types/dummy')
        self.assertEqual(
            response['_embedded']['item-type'][0]['id'], 'dummy')

    def test_get_item_type_invalid_id(self):
        item_type_id = 'some_id'
        cherrypy.request.path_info = '/item-types/%s' % item_type_id
        response = json.loads(
            self.item_type_controller.get_item_type(item_type_id)
        )
        self.assertTrue('data' not in response)
        self.assertTrue('messages' in response)
        self.assertEquals(len(response['messages']), 1)
        err = response['messages'][0]
        self.assertEquals(err['message'], 'Not found')
        self.assertEquals(
            err['_links']['self']['href'], cherrypy.request.path_info)
        self.assertEquals(err['type'], constants.INVALID_LOCATION_ERROR)

    def test_get_item_type_valid_id(self):
        item_type_id = 'dummy'
        cherrypy.request.path_info = '/item-types/%s' % item_type_id
        response = json.loads(
            self.item_type_controller.get_item_type(item_type_id)
        )
        self.assertEqual(
            response['_links']['self']['href'], '/item-types/dummy')
        self.assertEqual(response['id'], 'dummy')

    def test_get_item_type_valid_id_with_fields(self):
        item_type_id = 'bigger_dummy'
        cherrypy.request.path_info = '/item-types/%s' % item_type_id
        response = json.loads(
            self.item_type_controller.get_item_type(item_type_id)
        )
        self.assertEqual(
            response['_links']['self']['href'], '/item-types/bigger_dummy')
        self.assertEqual(response['id'], 'bigger_dummy')
