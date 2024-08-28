import unittest
import os

from litp.core.model_manager import ModelManager
from litp.xml.xml_loader import XmlLoader
from litp.core.model_type import ItemType
from litp.core.model_type import Child
from litp.core.model_type import Collection
from litp.core.model_type import RefCollection
from litp.core.model_type import Property
from litp.core.model_type import PropertyType


class Mock(object):
    pass


class XmlLoaderDefaultsTest(unittest.TestCase):
    def setUp(self):
        self.model = ModelManager()
        self.model.register_property_type(
            PropertyType("basic_string", ".*")
        )
        self.model.register_item_types([
            ItemType(
                "root",
                foo=Child("foo"),
            ),
            ItemType(
                "foo",
                bar1=Property("basic_string", default="foobar"),
                bar2=Property("basic_string"),
                baz=Child("foo"),
                coll1=Collection("foo"),
                coll2=RefCollection("foo"),
            )
        ])
        self.model.create_root_item("root")
        self.loader = XmlLoader(self.model, None)

    def test_defaults(self):
        xml_data = """\
<litp:foo xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xmlns:litp="http://www.ericsson.com/litp"
    xsi:schemaLocation="http://www.ericsson.com/litp litp.xsd"
    id="foo" version="LITP2">
    <foo id="baz" />
</litp:foo>
"""
        errors = self.loader.load("/", xml_data)
        self.assertEquals([], errors)

        item = self.model.get_item("/foo")
        self.assertEquals("foobar", item.bar1)
        self.assertEquals(None, item.bar2)

        item = self.model.get_item("/foo/baz")
        self.assertEquals("foobar", item.bar1)
        self.assertEquals(None, item.bar2)

        item = self.model.get_item("/foo/coll1")
        self.assertNotEquals(None, item)
        self.assertEquals({}, item.properties)

        item = self.model.get_item("/foo/coll2")
        self.assertNotEquals(None, item)
        self.assertEquals({}, item.properties)

    def test_defaults_collection_item(self):
        xml_data = """\
<litp:foo xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xmlns:litp="http://www.ericsson.com/litp"
    xsi:schemaLocation="http://www.ericsson.com/litp litp.xsd"
    id="foo" version="LITP2">
    <coll1 />
</litp:foo>
"""
        errors = self.loader.load("/", xml_data)
        self.assertEquals([], errors)

        item = self.model.get_item("/foo/coll1")
        self.assertNotEquals(None, item)
        self.assertEquals({}, item.properties)

    def test_defaults_ref_collection_item(self):
        xml_data = """\
<litp:foo xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xmlns:litp="http://www.ericsson.com/litp"
    xsi:schemaLocation="http://www.ericsson.com/litp litp.xsd"
    id="foo" version="LITP2">
    <coll2 />
</litp:foo>
"""
        errors = self.loader.load("/", xml_data)
        self.assertEquals([], errors)

        item = self.model.get_item("/foo/coll2")
        self.assertNotEquals(None, item)
        self.assertEquals({}, item.properties)
