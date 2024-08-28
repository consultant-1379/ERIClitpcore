
from lxml import etree
import unittest

from litp.core.model_manager import ModelManager
from litp.core.model_type import ItemType
from litp.core.model_type import Child
from litp.core.model_type import Collection
from litp.core.model_type import RefCollection
from litp.core.model_type import Reference
from litp.core.model_type import Property
from litp.core.model_type import PropertyType

from litp.xml.xml_exporter import XmlExporter


def _polish(tagname):
    tagname = tagname.split("}")[-1]
    return tagname


# TODO (xigomil) This one needs cleanup of ip-range types. Maybe.


class XmlExporterTest(unittest.TestCase):
    def setUp(self):
        self.model = ModelManager()
        self.model.register_property_type(
            PropertyType("basic_string", ".*"))
        self.model.register_property_type(
            PropertyType("integer", regex=r"^[0-9]+$"))
        self.model.register_property_type(
            PropertyType("hostname", regex=r"^[a-zA-Z0-9\.]+$"))
        self.model.register_property_type(
            PropertyType("network", regex=r".*"))
        self.model.register_property_type(
            PropertyType("ipv4_address", regex=r"^[0-9\.]+$"))
        self.model.register_property_type(
            PropertyType("mac_address",
                         regex=r"^([a-fA-F0-9]{2}(:)){5}([a-fA-F0-9]{2})$"))

        self.model.register_item_types([
            ItemType(
                "root",
                ms=Child("node"),
                infrastructure=Child("infrastructure"),
                nodes=Collection("node"),
                software=Child("software"),
            ),
            ItemType(
                "software",
                profiles=Collection("os-profile"),
                items=Collection("software-item"),
            ),
            ItemType(
                "node",
                hostname=Property("hostname", required=True),
                os=Reference("os-profile"),
                ipaddresses=RefCollection("ip-range"),
                ha_manager=Child("ha-manager"),
                system=Reference("system"),
                storage_profile=Reference("storage-profile"),
                network_profile=Reference("network-profile")
            ),
            ItemType(
                "profile",
                item_description="Base profile item.",
            ),
            ItemType(
                "os-profile",
                extend_item="profile",
                name=Property("basic_string"),
                distro=Property("basic_string", required=True),
                version=Property("basic_string"),
                items=RefCollection("software-item"),
                not_updatable=Property("basic_string", updatable_rest=False)
            ),
            ItemType(
                "software-item",
                name=Property("basic_string"),
            ),
            ItemType(
                "package",
                extend_item="software-item",
                version=Property("basic_string"),
            ),
            ItemType(
                "infrastructure",
                ranges=Collection("ip-range"),
            ),
            ItemType(
                "network-range",
                item_description="Base type for network addresses range."
            ),
            ItemType(
                "ip-range",
                "network-range",
                item_description="IP address range item.",
                network_name=Property(
                    "basic_string",
                    required=True,
                    prop_description="Network name for ip-range."
                    "This must be unique to each ip-range.",
                ),
                start=Property(
                    "ipv4_address",
                    required=True,
                    prop_description="Start address of ip-range.",
                ),
                end=Property(
                    "ipv4_address",
                    required=True,
                    prop_description="End address of ip-range.",
                ),
                subnet=Property(
                    "network",
                    required=True,
                    prop_description="Subnet for ip-range.",
                ),
                gateway=Property(
                    "ipv4_address",
                    prop_description="Gateway for ip-range.",
                ),
            ),
            ItemType(
                "nic",
                item_description="A network interface.",
                macaddress=Property(
                    "mac_address",
                    required=True,
                    prop_description="MAC address of this NIC"
                ),
                interface_name=Property(
                    "basic_string",
                    prop_description="Interface name for the NIC"
                ),
            ),
        ])
        self.model.create_root_item("root")
        self.model.create_item("software", "/software")
        self.model.create_item("infrastructure", "/infrastructure")

        self.exporter = XmlExporter(self.model)

    def _normalize_xml(self, doc):
        for element in doc.xpath('//*[./*]'):  # Search for parent elements
            element[:] = sorted(element, key=lambda x: x.tag)
        return doc

    def _compare_elements(self, expected, actual):
        expected_attribs = sorted(expected.attrib)
        actual_attribs = sorted(actual.attrib)
        self.assertEquals(expected_attribs, actual_attribs, "Expected %s in %s" % (expected.attrib, expected))
        self.assertEquals(expected.tag, actual.tag)
        self.assertEquals(expected.text, actual.text)
        self.assertEquals(len(expected.getchildren()), len(actual.getchildren()))
        for index, child in enumerate(expected.getchildren()):
            self._compare_elements(child, actual.getchildren()[index])

    def _compare_xml(self, expected, actual):
        parser = etree.XMLParser(remove_blank_text=True)
        a = self._normalize_xml(etree.fromstring(expected, parser))
        b = self._normalize_xml(etree.fromstring(actual, parser))
        #print '------'
        #print expected
        #print '------'
        #print actual
        #print '------'
        self._compare_elements(a, b)

    def _setup_additional_types(self):
        self.model.register_item_types([
            ItemType(
                "system",
                serial=Property(
                    "basic_string",
                ),
                system_name=Property(
                    "basic_string",
                    required=True
                ),
                disks=Collection("disk"),
                network_interfaces=Collection("nic"),
            ),
            ItemType(
                "system-provider",
                item_description="Base system-provider item.",
            ),
            ItemType("mock-system", extend_item="system"),
            ItemType("storage-profile"),
            ItemType("network-profile-base", name=Property("basic_string")),
            ItemType("network-profile",
                     extend_item="network-profile-base",
                     management_network=Property("basic_string"),
                     bridges=Collection("bridges"),
                     interfaces=Collection("interface"),
                     networks=Collection("network"))

        ])

    def test_get_as_xml(self):
        expected_result = \
"""
<?xml version='1.0' encoding='utf-8' ?>
<litp:root xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" \
    xmlns:litp="http://www.ericsson.com/litp" \
    xsi:schemaLocation="http://www.ericsson.com/litp litp-xml-schema/litp.xsd" \
    id="root">
  <litp:root-nodes-collection id="nodes"/>
  <litp:infrastructure id="infrastructure">
    <litp:infrastructure-ranges-collection id="ranges"/>
  </litp:infrastructure>
  <litp:software id="software">
    <litp:software-items-collection id="items">
      <litp:package id="t1">
        <name>telnet</name>
      </litp:package>
    </litp:software-items-collection>
    <litp:software-profiles-collection id="profiles">
      <litp:os-profile id="test-profile">
        <version>6.4</version>
        <name>sample-profile</name>
        <distro>rhel-x86_64</distro>
        <litp:os-profile-items-collection id="items"/>
        <not_updatable>foobar<!--note: this property is not updatable--></not_updatable>
      </litp:os-profile>
    </litp:software-profiles-collection>
  </litp:software>
</litp:root>
"""
        self.model.create_item("package", "/software/items/t1",
                                name="telnet")

        self.model.create_item(
            "os-profile", "/software/profiles/test-profile",
            name="sample-profile",
            distro="rhel-x86_64",
            version="6.4",
            not_updatable="foobar")

        self._compare_xml(expected_result.strip(), self.exporter.get_as_xml("/"))

    def test_get_partial_xml(self):
        expected_result = """
<?xml version='1.0' encoding='utf-8' ?>
<litp:ip-range id="ip_ranges" \
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"\
    xmlns:litp="http://www.ericsson.com/litp" \
    xsi:schemaLocation=\
"http://www.ericsson.com/litp litp-xml-schema/litp.xsd">
    <network_name>nodes</network_name>
    <start>10.10.10.1</start>
    <end>10.10.10.254</end>
    <subnet>10.10.10.0/24</subnet>
    <gateway>10.10.10.5</gateway>
</litp:ip-range>"""

        self.model.create_item(
            "ip-range",
            "/infrastructure/ranges/ip_ranges",
            network_name="nodes",
            start="10.10.10.1",
            end="10.10.10.254",
            subnet="10.10.10.0/24",
            gateway="10.10.10.5")
        self._compare_xml(expected_result.strip(),  self.exporter.get_as_xml("/infrastructure/ranges/ip_ranges"))

    def test_get_as_base_type_sorted(self):
        expected_result = \
"""
<?xml version='1.0' encoding='utf-8'?>
<litp:node xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:litp="http://www.ericsson.com/litp" xsi:schemaLocation="http://www.ericsson.com/litp litp-xml-schema/litp.xsd" id="node1">
  <hostname>node1</hostname>
  <litp:node-ipaddresses-collection id="ipaddresses"/>
  <litp:os-profile-inherit source_path="/software/profiles/os" id="os">
    <name>sample-profile</name>
    <version>rhel6</version>
    <litp:os-profile-items-collection-inherit source_path="/software/profiles/os/items" id="items"/>
  </litp:os-profile-inherit>
</litp:node>
"""

        self._setup_additional_types()

        self.model.create_item("storage-profile-base",
                               "/infrastructure/storage/storage_profiles/profile_1",)
        self.model.create_item("system",
                               "/infrastructure/systems/system1",
                               system_name="SYS1")

        self.model.create_item(
            "os-profile", "/software/profiles/os",
            name="name",
            distro="distro")

        self.model.create_item(
            "node", "/nodes/node1",
            hostname="node1")

        self.model.create_inherited(
            "/infrastructure/systems/system1",
            "/nodes/node1/system")

        self.model.create_inherited(
            "/software/profiles/os",
            "/nodes/node1/os",
            name="sample-profile",
            version="rhel6")

        self.model.create_inherited(
            "/infrastructure/storage/storage_profiles/profile_1",
            "/nodes/node1/storage_profile",)

        doc = self.exporter.get_as_xml("/nodes/node1")
        self._compare_xml(expected_result.strip(), doc)

    def test_handle_non_string_properties(self):
        expected_result = """
<?xml version='1.0' encoding='utf-8'?>
<litp:root xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:litp="http://www.ericsson.com/litp" xsi:schemaLocation="http://www.ericsson.com/litp litp-xml-schema/litp.xsd" id="root">
  <litp:infrastructure id="infrastructure">
    <litp:infrastructure-ranges-collection id="ranges"/>
  </litp:infrastructure>
  <litp:root-nodes-collection id="nodes"/>
  <litp:software id="software">
    <litp:software-items-collection id="items">
      <litp:test-item id="test-item">
        <field>50</field>
      </litp:test-item>
    </litp:software-items-collection>
    <litp:software-profiles-collection id="profiles"/>
  </litp:software>
</litp:root>
"""
        self.model.register_item_types([
            ItemType(
                "test-item",
                extend_item="software-item",
                field=Property(
                    "integer",
                    default="100"
                ),
            )
        ])

        item = self.model.create_item(
            "test-item", "/software/items/test-item",
            field=50)

        self.assertEquals(["field"],
            self.exporter._properties_for_type(item.item_type))

        self._compare_xml(expected_result.strip(), self.exporter.get_as_xml("/"))

    def test_jumbled_field_names(self):
        """
        Covers issue LITPCDS-11023.
        Backward compatibility enforces field sorting logic implemented in
        schemawriter. The order of tags in export is mixed (naturally
        "direct" and "cb" has to change places).
        """
        expected = """
<?xml version='1.0' encoding='utf-8'?>
<litp:test-item xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:litp="http://www.ericsson.com/litp" xsi:schemaLocation="http://www.ericsson.com/litp litp-xml-schema/litp.xsd" id="test">
  <litp:ca id="ca"/>
  <litp:test-item-direct-collection id="direct"/>
  <litp:pz id="cb"/>
  <litp:test-item-salt-collection id="salt"/>
</litp:test-item>
"""
        self.model.register_item_types([
                ItemType('ca', extend_item='software-item'),
                ItemType('pz', extend_item='software-item'),
                ItemType(
                    'test-item',
                    extend_item='software-item',
                    ca=Child('ca'),
                    cb=Child('pz'),
                    direct=Collection("software-item"),
                    salt=Collection("software-item"))
                ])
        self.model.create_item('test-item', '/software/items/test')
        self.model.create_item('ca', '/software/items/test/ca')
        self.model.create_item('pz', '/software/items/test/cb')
        actual = self.exporter.get_as_xml('/software/items/test')
        self.assertEqual(expected.strip(), actual.strip())
