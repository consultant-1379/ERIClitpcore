import json
import unittest
from litp.core import litp_serialize


@litp_serialize.serialized
def test_func():
    return {'lala': 'foo'}

class MockObject(object):
    def __init__(self):
        self.variable = 42

class SerializerTest(unittest.TestCase):
    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_serializer_object(self):
        obj = MockObject()
        str_JSON = litp_serialize.do_serialize(obj)
        obj_JSON = json.loads(str_JSON)
        self.assertEquals(
            obj_JSON['variable'],
            42,
            msg="Test class did not survive JSON round-trip intact")

    def test_serializer_string(self):
        obj = "Test String"
        str_JSON = litp_serialize.do_serialize(obj)
        self.assertEquals(
            str_JSON, 
            obj,
            msg="String did not survive JSON round-trip intact")

    def test_serializer_decorated_function(self):
        self.assertEquals(
            '{\n    "lala": "foo"\n}',
            test_func()
            )
