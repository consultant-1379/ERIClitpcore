import os
import unittest
import cStringIO

from mock import patch, MagicMock, call
from lxml import etree
from lxml.etree import Element, ElementTree

from litp.core.extension import ModelExtension
from litp.core.plugin import Plugin
from litp.core.model_type import PropertyType, ItemType, \
    Property, Collection, Child, Reference, RefCollection

from litp.core import schemawriter
from litp.core.schemawriter import SchemaWriter, NS, NS_PREFIX, NS_URL
from litp.core.exceptions import SchemaWriterException, FieldSorterException


property_types = [
    PropertyType("any_string", regex="^.*$"),
    PropertyType("basic_string", regex="^[a-zA-Z0-9]+$"),
]
property_types_map = dict([(_t.property_type_id, _t) for _t in property_types])

item_types = [
    ItemType(
        "baz",
        s1=Property("basic_string"),
    ),
    ItemType(
        "foo1",
        s1=Property("any_string"),
        s2=Property("basic_string"),
    ),
    ItemType(
        "foo2",
        extend_item="foo1",
        thing=Child("bar"),
        things=Collection("bar"),
        refthing=Reference("bar"),
        refthings=RefCollection("bar"),
    ),
    ItemType("bar", item_description="foobar"),

    ItemType("foo10", item_description="foo"),
    ItemType("foo11"),
    ItemType("foo12"),
    ItemType(
        "link-foo11",
        foo11=Reference("foo11")
    ),
    ItemType(
        "extend-foo12",
        extend_item="foo12"
    ),

    ItemType("test_item_type"),
]
item_types_map = dict([(_t.item_type_id, _t) for _t in item_types])


def parse_xml(xml):
    parser = etree.XMLParser(remove_blank_text=True)
    return wrap_elements(etree.fromstring(xml, parser=parser).getchildren())


def wrap_elements(elements):
    element = Element(NS + "schema", nsmap={NS_PREFIX: NS_URL})
    element.extend(elements)
    return element


class FooBarPlugin(Plugin):

    def register_property_types(self):
        return list(property_types)

    def register_item_types(self):
        return list(item_types)


class FooBarExtension(ModelExtension):

    def define_property_types(self):
        return list(property_types)

    def define_item_types(self):
        return list(item_types)

    def __eq__(self, other):
        # We check strict equality of types, because
        # is instance will allow subclasses which we don't
        # want in test_process_config_dir
        if type(other) == FooBarExtension:
            return True
        return False


def cmp_elements(e1, e2):
    ret = e1.prefix == e2.prefix
    if not ret:
        return False
    ret = e1.tag == e2.tag
    if not ret:
        return False
    ret = e1.tail == e2.tail
    if not ret:
        return False
    ret = e1.text == e2.text
    if not ret:
        return False

    ret = e1.items() == e2.items()
    if not ret:
        return False

    ret = cmp_list_of_elements(list(e1), list(e2))
    if not ret:
        return False
    return True


def cmp_list_of_elements(l1, l2):
    ret = len(l1) == len(l2)
    if not ret:
        return False
    iter1 = iter(l1)
    iter2 = iter(l2)

    try:
        while True:
            e1 = iter1.next()
            e2 = iter2.next()
            ret = cmp_elements(e1, e2)
            if not ret:
                return False
    except StopIteration:
        pass

    return True


HR = "-" * 40

EXT_NAME = "foobar"


class SchemaWriterTest(unittest.TestCase):

    def assertXmlEquals(self, e1, e2):
        if cmp_elements(e1, e2):
            return

        f1 = cStringIO.StringIO()
        ElementTree(e1).write(f1, pretty_print=True)
        f2 = cStringIO.StringIO()
        ElementTree(e2).write(f2, pretty_print=True)
        self.fail("\n".join(
            ["XMLs don't match:\n", HR, f1.getvalue(), HR, f2.getvalue()]))

    def setUp(self):
        self.schemawriter = SchemaWriter("/tmp/litp-xsd", "litp/etc/plugins")

    def initialize_schemawriter(self):
        def parse_config_file(path):
            return EXT_NAME, "litp.FooBar"

        def get_extension_class(pkg, name):
            return FooBarExtension

        self.schemawriter._parse_config_file = parse_config_file
        self.schemawriter._get_extension_class = get_extension_class
        self.schemawriter._process_config_dir("")

    def test_normalize_regex(self):
        ret = self.schemawriter._normalize_regex("^.*$")
        self.assertEquals(".*", ret)

    def test_parse_config_file_plugin(self):
        def read_config_file(config, path):
            config.add_section("plugin")
            config.set("plugin", "name", "plugin-name")
            config.set("plugin", "class", "plugin-class")

        self.schemawriter._read_config_file = read_config_file
        ret = self.schemawriter._parse_config_file("configfile")
        self.assertEquals(("plugin-name", "plugin-class"), ret)

    def test_parse_config_file_extension(self):
        def read_config_file(config, path):
            config.add_section("extension")
            config.set("extension", "name", "extension-name")
            config.set("extension", "class", "extension-class")

        self.schemawriter._read_config_file = read_config_file
        ret = self.schemawriter._parse_config_file("configfile")
        self.assertEquals(("extension-name", "extension-class"), ret)

    def test_parse_config_file_invalid_1(self):
        def read_config_file(config, path):
            pass

        self.schemawriter._read_config_file = read_config_file
        self.assertRaises(
            SchemaWriterException,
            self.schemawriter._parse_config_file, "configfile")

    def test_parse_config_file_invalid_2(self):
        def read_config_file(config, path):
            config.add_section("extension")
            config.set("extension", "class", "extension-class")

        self.schemawriter._read_config_file = read_config_file
        self.assertRaises(
            SchemaWriterException,
            self.schemawriter._parse_config_file, "configfile")

    def test_parse_config_file_invalid_3(self):
        def read_config_file(config, path):
            config.add_section("extension")
            config.set("extension", "name", "extension-name")

        self.schemawriter._read_config_file = read_config_file
        self.assertRaises(
            SchemaWriterException,
            self.schemawriter._parse_config_file, "configfile")

    def test_processing_same_class(self):
        self.initialize_schemawriter()
        self.assertRaises(
            SchemaWriterException, self.schemawriter._process_config_dir, "")

    def test_get_types_plugin(self):
        types = self.schemawriter._get_types(FooBarPlugin())
        self.assertEquals(sorted(property_types + item_types), sorted(types))

    def test_get_types_extension(self):
        types = self.schemawriter._get_types(FooBarExtension())
        self.assertEquals(sorted(property_types + item_types), sorted(types))

    def test_get_types_invalid(self):
        self.assertRaises(
            SchemaWriterException, self.schemawriter._get_types, "")

    def test_get_type_id_property_type(self):
        t = PropertyType("foobar", regex="^.*$")
        type_id = self.schemawriter._get_type_id(t)
        self.assertEquals("_foobar", type_id)

    def test_get_type_id_item_type(self):
        t = ItemType("foobar")
        type_id = self.schemawriter._get_type_id(t)
        self.assertEquals("foobar", type_id)

    def test_get_type_id_invalid(self):
        self.assertRaises(
            SchemaWriterException, self.schemawriter._get_type_id, "")

    def test_process_config_dir(self):
        self.initialize_schemawriter()

        self.assertEquals(set(["FooBar"]), self.schemawriter._ext_names)
        self.assertEquals(set(
            ["litp.FooBar"]), self.schemawriter._ext_class_names)

        self.assertEquals(
            {FooBarExtension: FooBarExtension()},
            self.schemawriter._ext_instances)
        self.assertEquals(sorted(property_types + item_types), sorted(
            self.schemawriter._ext_types[FooBarExtension]))

    def test_process_config_dir_raises_attribute_error(self):
        def raise_AttributeError(pkg, name):
            raise AttributeError

        self.schemawriter._get_extension_class = raise_AttributeError
        self.schemawriter._parse_config_file = lambda path: ("foobar",
                "litp.FooBar")

        self.assertTrue(self.schemawriter._process_config_dir("") is None)

    def test_process_config_dir_raises_import_error(self):
        def raise_ImportError(pkg, name):
            raise ImportError

        self.schemawriter._get_extension_class = raise_ImportError
        self.schemawriter._parse_config_file = lambda path: ("foobar",
                "litp.FooBar")

        self.assertTrue(self.schemawriter._process_config_dir("") is None)

    def test_get_extension_class(self):
        class_module = "litp.core.schemawriter"
        class_name = "SchemaWriter"
        # Try dynamically loading schemawriter class
        class_type = self.schemawriter._get_extension_class(class_module,
                class_name)

        self.assertEqual(SchemaWriter, class_type)

    def test_validate_discovered_items_ok(self):
        self.initialize_schemawriter()
        try:
            self.schemawriter._validate_discovered_items()
        except SchemaWriterException:
            self.fail("SchemaWriterException raised on good data")

    def test_validate_discovered_items_bad_parent(self):
        class BadExtension(FooBarExtension):
            def define_item_types(self):
                return list(item_types) + [ItemType("badItem",
                                           extend_item="nonexistant")]

        def parse_config_file_bad(path):
            return "BadExtension", "litp.BadExtension"

        def get_extension_class_bad(pkg, name):
            return BadExtension

        self.schemawriter._parse_config_file = parse_config_file_bad
        self.schemawriter._get_extension_class = get_extension_class_bad
        self.schemawriter._process_config_dir("")
        self.assertRaises(SchemaWriterException,
            self.schemawriter._validate_discovered_items)

    def test_validate_discovered_items_unknown_field_type(self):
        self.initialize_schemawriter()
        self.schemawriter._sorter.get_field_type_id = lambda field: "nonexistant"
        self.assertRaises(SchemaWriterException,
            self.schemawriter._validate_discovered_items)

    def test_validate_discovered_items_overwrites_field_type(self):
        class BadExtension(FooBarExtension):
            def define_item_types(self):
                return list(item_types) + [ItemType("bad_foo1_child",
                                           extend_item="foo1",
                                           s1=Property("basic_string"))]

        def parse_config_file_bad(path):
            return "BadExtension", "litp.BadExtension"

        def get_extension_class_bad(pkg, name):
            return BadExtension

        self.schemawriter._parse_config_file = parse_config_file_bad
        self.schemawriter._get_extension_class = get_extension_class_bad
        self.schemawriter._process_config_dir("")
        self.assertRaises(SchemaWriterException,
            self.schemawriter._validate_discovered_items)

    def test_create_documentation_elements(self):
        ret = wrap_elements(
            self.schemawriter._create_documentation_elements(ItemType("foobar", item_description="foobar")))
        xml = """\
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
    <xs:annotation>
        <xs:documentation>foobar</xs:documentation>
    </xs:annotation>
</xs:schema>"""
        expected = parse_xml(xml)
        self.assertXmlEquals(expected, ret)

    def test_create_elements_property_type(self):
        self.initialize_schemawriter()

        t = property_types_map["basic_string"]
        ret = wrap_elements(
            self.schemawriter._create_elements_property_type(t))
        xml = """\
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
    <xs:simpleType name="_basic_string-type">
        <xs:restriction base="xs:string">
            <xs:pattern value="[a-zA-Z0-9]+" />
        </xs:restriction>
    </xs:simpleType>
</xs:schema>"""
        expected = parse_xml(xml)
        self.assertXmlEquals(expected, ret)

    def test_create_elements_item_type(self):
        self.initialize_schemawriter()

        t = item_types_map["foo10"]
        ret = wrap_elements(self.schemawriter._create_elements_item_type(t))
        xml = \
"""
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:include schemaLocation="../litp-base.xsd"/>
  <xs:complexType name="foo10-type">
    <xs:annotation>
      <xs:documentation>foo</xs:documentation>
    </xs:annotation>
    <xs:complexContent>
      <xs:extension base="baseitem-type">
        <xs:sequence/>
      </xs:extension>
    </xs:complexContent>
  </xs:complexType>
  <xs:element name="foo10" type="foo10-type"/>
  <xs:complexType name="foo10-inherit-type">
    <xs:annotation>
      <xs:documentation>foo</xs:documentation>
    </xs:annotation>
    <xs:complexContent>
      <xs:extension base="baseitem-inherit-type">
        <xs:sequence/>
      </xs:extension>
    </xs:complexContent>
  </xs:complexType>
  <xs:element name="foo10-inherit" type="foo10-inherit-type"/>
</xs:schema>
"""
        expected = parse_xml(xml)
        self.assertXmlEquals(expected, ret)

    def test_get_fields_with_details(self):
        self.schemawriter._type_instances.update({
            "_bar1": None,
            "bar2": None,
            "bar3": None,
            "bar4": None,
            "bar5": None
        })

        fields = {
            "foo1": Property("bar1"),
            "foo2": Child("bar2"),
            "foo3": Collection("bar3"),
            "foo4": Reference("bar4"),
            "foo5": RefCollection("bar5"),
        }
        model_type = ItemType("foobar", **fields)
        details = self.schemawriter._sorter.get_fields_with_details(model_type)
        details = [tup[0:2] for tup in details]

        expected = [
            ("foo1", "_bar1"),
            ("bar2", "bar2"),
            ("bar4-inherit", "bar4"),
            ("foo3", "bar3"),
            ("foo5", "bar5"),
        ]

        self.assertEquals(expected, details)

        fields = {
            "foo": ""
        }
        model_type = ItemType("foobar")
        model_type.structure = fields
        self.assertRaises(
            FieldSorterException, self.schemawriter._sorter.get_fields_with_details,
            model_type)

    def test_create_elements_field_property(self):
        self.initialize_schemawriter()

        fields = {"foo": Property("any_string", prop_description="foobar")}
        model_type = ItemType("foobar", **fields)
        details = self.schemawriter._sorter.get_fields_with_details(model_type)

        ret = wrap_elements(
            self.schemawriter._create_elements_field(model_type, *details[0][:3]))
        xml = """\
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
    <xs:element name="foo" type="_any_string-type" minOccurs="0">
        <xs:annotation>
            <xs:documentation>foobar</xs:documentation>
        </xs:annotation>
    </xs:element>
</xs:schema>"""
        expected = parse_xml(xml)
        self.assertXmlEquals(expected, ret)

        ret = wrap_elements(
            self.schemawriter._create_elements_field(model_type, *details[0][:3], is_inherit_type=True))
        xml = """\
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
    <xs:element name="foo" type="_any_string-type" minOccurs="0">
        <xs:annotation>
            <xs:documentation>foobar</xs:documentation>
        </xs:annotation>
    </xs:element>
</xs:schema>"""
        expected = parse_xml(xml)
        self.assertXmlEquals(expected, ret)

        fields = {"foo": Property("any_string", required=True)}
        model_type = ItemType("foobar", **fields)
        details = self.schemawriter._sorter.get_fields_with_details(model_type)

        ret = wrap_elements(
            self.schemawriter._create_elements_field(model_type, *details[0][:3]))
        xml = """\
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
    <xs:element name="foo" type="_any_string-type" />
</xs:schema>"""
        expected = parse_xml(xml)
        self.assertXmlEquals(expected, ret)

        fields = {"foo": Property("any_string", required=True, default="bar")}
        model_type = ItemType("foobar", **fields)
        details = self.schemawriter._sorter.get_fields_with_details(model_type)

        ret = wrap_elements(
            self.schemawriter._create_elements_field(model_type, *details[0][:3]))
        xml = """\
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
    <xs:element name="foo" type="_any_string-type" minOccurs="0" default="bar"/>
</xs:schema>"""
        expected = parse_xml(xml)
        self.assertXmlEquals(expected, ret)

    def test_create_elements_field_unknown(self):
        self.initialize_schemawriter()
        self.assertRaises(
            SchemaWriterException, self.schemawriter._create_elements_field,
            "foo", "bar", "", "")
        self.assertRaises(
            SchemaWriterException, self.schemawriter._create_elements_field,
            "foo", "bar", "baz", "")

    def test_get_extension_class(self):
        loaded_class = self.schemawriter._get_extension_class(
            "litp.core.schemawriter", "SchemaWriter")
        self.assertEquals(SchemaWriter, loaded_class)

    def test_generate_schemas(self):
        class MockOs(object):

            class Path(object):

                def __init__(self, mockos):
                    self._parent = mockos

                def join(self, *args):
                    return os.path.join(*args)

                def relpath(self, path1, path2):
                    return os.path.relpath(path1, path2)

                def dirname(self, path):
                    return os.path.dirname(path)

                def exists(self, path):
                    # print "################### exists [%s]" % path
                    self._parent._mock("exists", path)
                    return path in self._parent._dirs_created

            def __init__(self, mock):
                self.path = MockOs.Path(self)
                self._dirs_created = set()
                self._mock = mock

            def mkdir(self, path):
                # print "################### mkdir [%s]" % path
                self._mock("mkdir", path)
                self._dirs_created.add(path)

        class Patcher(object):

            def __init__(self):
                self._mock = MagicMock()
                self._patchers = set()
                self._patchers.add(patch("__builtin__.open", new=self.open))
                self._patchers.add(patch(
                    "litp.core.schemawriter.os", new=MockOs(self._mock)))

            def open(self, path, mode):
                # print "################### open [%s]" % path
                self._mock("open", path, mode)
                return MagicMock()

            def __enter__(self):
                for patcher in self._patchers:
                    patcher.start()
                return self

            def __exit__(self, *args):
                for patcher in self._patchers:
                    patcher.stop()

        self.initialize_schemawriter()
        with Patcher() as p:
            self.schemawriter._generate_schemas()

            basepath = self.schemawriter._xsd_basepath
            calls = []
            calls.append(call("exists", basepath))
            calls.append(call("mkdir", basepath))
            calls.append(call("exists", os.path.join(basepath, EXT_NAME)))
            calls.append(call("mkdir", os.path.join(basepath, EXT_NAME)))
            for t in property_types:
                calls.append(call("open", os.path.join(
                    basepath, EXT_NAME, "_" + t.property_type_id + ".xsd"),
                    "w"))
            for t in item_types:
                calls.append(call("open", os.path.join(
                    basepath, EXT_NAME, t.item_type_id + ".xsd"), "w"))
            calls.append(call("open", os.path.join(
                basepath, EXT_NAME + ".xsd"), "w"))
            calls.append(call("open", os.path.join(
                basepath, schemawriter.BASE_XSD), "w"))
            calls.append(call("open", os.path.join(
                basepath, schemawriter.MAIN_XSD), "w"))

            self.assertEquals(calls, p._mock.mock_calls)

    def test_new_collections(self):
        self.initialize_schemawriter()
        root = Element(NS + "schema", nsmap={NS_PREFIX: NS_URL})
        model_type = item_types_map["foo2"]
        ret = wrap_elements(self.schemawriter._create_elements_item_type(model_type))
        xml = \
"""
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:include schemaLocation="bar.xsd"/>
  <xs:include schemaLocation="foo1.xsd"/>
  <xs:include schemaLocation="../litp-base.xsd"/>
  <xs:complexType name="foo2-type">
    <xs:complexContent>
      <xs:extension base="foo1-type">
        <xs:sequence>
          <xs:element ref="bar" minOccurs="0">
            <xs:annotation>
              <xs:documentation>Child of bar</xs:documentation>
            </xs:annotation>
          </xs:element>
          <xs:element ref="bar-inherit" minOccurs="0">
            <xs:annotation>
              <xs:documentation>Reference to bar</xs:documentation>
            </xs:annotation>
          </xs:element>
          <xs:element ref="foo2-refthings-collection" minOccurs="0"/>
          <xs:element ref="foo2-things-collection" minOccurs="0"/>
        </xs:sequence>
      </xs:extension>
    </xs:complexContent>
  </xs:complexType>
  <xs:element name="foo2" type="foo2-type" substitutionGroup="foo1"/>
  <xs:complexType name="foo2-inherit-type">
    <xs:complexContent>
      <xs:extension base="foo1-inherit-type">
        <xs:sequence>
          <xs:element ref="bar-inherit" minOccurs="0">
            <xs:annotation>
              <xs:documentation>Child of bar</xs:documentation>
            </xs:annotation>
          </xs:element>
          <xs:element ref="bar-inherit" minOccurs="0">
            <xs:annotation>
              <xs:documentation>Reference to bar</xs:documentation>
            </xs:annotation>
          </xs:element>
          <xs:element ref="foo2-refthings-collection-inherit" minOccurs="0"/>
          <xs:element ref="foo2-things-collection-inherit" minOccurs="0"/>
        </xs:sequence>
      </xs:extension>
    </xs:complexContent>
  </xs:complexType>
  <xs:element name="foo2-inherit" type="foo2-inherit-type" substitutionGroup="foo1-inherit"/>
  <xs:complexType name="foo2-refthings-collection-type">
    <xs:annotation>
      <xs:documentation>Ref-collection of bar **Deprecated: basecollection-inherit-type has been deprecated. Please use basecollection-type instead.**</xs:documentation>
    </xs:annotation>
    <xs:complexContent>
      <xs:extension base="basecollection-inherit-type">
        <xs:sequence>
          <xs:element ref="bar-inherit" minOccurs="0" maxOccurs="9999"/>
        </xs:sequence>
        <xs:attribute name="id" use="required">
          <xs:simpleType>
            <xs:restriction base="xs:string">
              <xs:pattern value="refthings"/>
            </xs:restriction>
          </xs:simpleType>
        </xs:attribute>
      </xs:extension>
    </xs:complexContent>
  </xs:complexType>
  <xs:element name="foo2-refthings-collection" type="foo2-refthings-collection-type"/>
  <xs:complexType name="foo2-refthings-collection-inherit-type">
    <xs:annotation>
      <xs:documentation>Ref-collection of bar **Deprecated: basecollection-inherit-type has been deprecated. Please use basecollection-type instead.**</xs:documentation>
    </xs:annotation>
    <xs:complexContent>
      <xs:extension base="basecollection-inherit-type">
        <xs:sequence>
          <xs:element ref="bar-inherit" minOccurs="0" maxOccurs="9999"/>
        </xs:sequence>
        <xs:attribute name="id" use="required">
          <xs:simpleType>
            <xs:restriction base="xs:string">
              <xs:pattern value="refthings"/>
            </xs:restriction>
          </xs:simpleType>
        </xs:attribute>
        <xs:attribute name="source_path" use="required">
          <xs:simpleType>
            <xs:restriction base="xs:string">
              <xs:pattern value="[a-zA-Z0-9_\-/]+"/>
            </xs:restriction>
          </xs:simpleType>
        </xs:attribute>
      </xs:extension>
    </xs:complexContent>
  </xs:complexType>
  <xs:element name="foo2-refthings-collection-inherit" type="foo2-refthings-collection-inherit-type"/>
  <xs:complexType name="foo2-things-collection-type">
    <xs:annotation>
      <xs:documentation>Collection of bar</xs:documentation>
    </xs:annotation>
    <xs:complexContent>
      <xs:extension base="basecollection-type">
        <xs:sequence>
          <xs:element ref="bar" minOccurs="0" maxOccurs="9999"/>
        </xs:sequence>
        <xs:attribute name="id" use="required">
          <xs:simpleType>
            <xs:restriction base="xs:string">
              <xs:pattern value="things"/>
            </xs:restriction>
          </xs:simpleType>
        </xs:attribute>
      </xs:extension>
    </xs:complexContent>
  </xs:complexType>
  <xs:element name="foo2-things-collection" type="foo2-things-collection-type"/>
  <xs:complexType name="foo2-things-collection-inherit-type">
    <xs:annotation>
      <xs:documentation>Collection of bar</xs:documentation>
    </xs:annotation>
    <xs:complexContent>
      <xs:extension base="basecollection-type">
        <xs:sequence>
          <xs:element ref="bar-inherit" minOccurs="0" maxOccurs="9999"/>
        </xs:sequence>
        <xs:attribute name="id" use="required">
          <xs:simpleType>
            <xs:restriction base="xs:string">
              <xs:pattern value="things"/>
            </xs:restriction>
          </xs:simpleType>
        </xs:attribute>
        <xs:attribute name="source_path" use="required">
          <xs:simpleType>
            <xs:restriction base="xs:string">
              <xs:pattern value="[a-zA-Z0-9_\-/]+"/>
            </xs:restriction>
          </xs:simpleType>
        </xs:attribute>
      </xs:extension>
    </xs:complexContent>
  </xs:complexType>
  <xs:element name="foo2-things-collection-inherit" type="foo2-things-collection-inherit-type"/>
</xs:schema>
"""
        expected = parse_xml(xml)
        self.assertXmlEquals(expected, ret)


class FieldSorterTestCase(unittest.TestCase):
    def setUp(self):
        self.schemawriter = SchemaWriter("/tmp/litp-xsd", "litp/etc/plugins")

    def initialize_schemawriter(self):
        def parse_config_file(path):
            return EXT_NAME, "litp.FooBar"

        def get_extension_class(pkg, name):
            return FooBarExtension

        self.schemawriter._parse_config_file = parse_config_file
        self.schemawriter._get_extension_class = get_extension_class
        self.schemawriter._process_config_dir("")

    def test_get_field_type_id_property(self):
        prop = Property("testProperty")
        self.assertEquals("_testProperty",
            self.schemawriter._sorter.get_field_type_id(prop))

    def test_get_field_type_id_raises(self):
        self.assertRaises(FieldSorterException,
                self.schemawriter._sorter.get_field_type_id, object())

    def test_get_fields_with_details_01(self):
        self.initialize_schemawriter()
        item = item_types_map['extend-foo12']
        self.assertEquals([],
            self.schemawriter._sorter.get_fields_with_details(item))

    def test_get_fields_with_details_02(self):
        self.initialize_schemawriter()
        item = item_types_map["baz"]
        self.assertEquals([("s1", "_basic_string", Property("basic_string"))],
            [x[:3] for x in self.schemawriter._sorter.get_fields_with_details(item)])

    def test_get_fields_with_details_raises(self):
        item = item_types_map["baz"]
        self.assertRaises(FieldSorterException,
            self.schemawriter._sorter.get_fields_with_details, item)

    def test_get_element_name_01(self):
        name = self.schemawriter._sorter.get_element_name(
            "foo", "bar", Property("bar"))
        self.assertEquals("foo", name)

    def test_get_element_name_02(self):
        name = self.schemawriter._sorter.get_element_name("foo", "bar", Child("bar"))
        self.assertEquals("bar", name)

    def test_get_element_name_03(self):
        name = self.schemawriter._sorter.get_element_name(
            "foo", "bar", Collection("bar"))
        self.assertEquals("foo", name)

    def test_get_element_name_04(self):
        name = self.schemawriter._sorter.get_element_name(
            "foo", "bar", Reference("bar"))
        self.assertEquals("bar-inherit", name)

    def test_get_element_name_05(self):
        name = self.schemawriter._sorter.get_element_name(
            "foo", "bar", RefCollection("bar"))
        self.assertEquals("foo", name)

    def test_get_element_name_07(self):
        self.assertRaises(
            FieldSorterException, self.schemawriter._sorter.get_element_name,
            "foo", "bar", "")
