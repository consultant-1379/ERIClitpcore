from lxml import etree
import os
import socket
import unittest
from mock import Mock

from litp.core.model_manager import ModelManager
from litp.core.model_type import Collection
from litp.core.model_type import ItemType
from litp.core.model_type import Property
from litp.core.model_type import View
from litp.core.model_type import PropertyType
from litp.core.validators import ValidationError
from litp.extensions.core_extension import CoreExtension
from litp.extensions.core_extension import MSValidator
from litp.xml.xml_loader import XmlLoader


class XmlLoaderTest(unittest.TestCase):
    def setUp(self):
        MSValidator.get_hostname = lambda s: "ms1"
        socket.get_hostname = lambda s: "ms1"
        self.model = ModelManager()
        core_extension = CoreExtension()
        self.model.register_property_types(core_extension.define_property_types())
        self.model.register_item_types(core_extension.define_item_types())
        self.model.register_item_type(
            ItemType(
                "os-profile2",
                extend_item="os-profile",
                foo=Property("basic_string", updatable_rest=False),
                foo2=Property("basic_string"),
                foo3=Property("basic_string"),
                misterview=View('basic_string', self.mock_view),
            )
        )
        self.model.create_root_item("root")
        self.model.update_item('/ms', hostname='ms1')
        self.loader = XmlLoader(self.model, None)

    def mock_view(self):
        return "Hello"

    def _load_xml_data(self, filename):
        return open(os.path.join(os.path.dirname(__file__),filename)).read()

    def _load_xml_element(self, filename):
        return etree.XML(self._load_xml_data(filename))

    def test_load_node(self):
        cluster_path = "/deployments/dep1/clusters/cluster1"
        self.model.create_item("deployment", "/deployments")
        self.model.create_item("deployment", "/deployments/dep1")
        self.model.create_item("cluster", cluster_path)
        self.model.create_item("os-profile2",
                               "/software/profiles/rhel_6_4",
                               name="sample_profile",
                               path="/var", foo="baz")

        xml_data = open(
            os.path.join(os.path.dirname(__file__),
                         "node1.xml")).read()
        errors = self.loader.load(cluster_path + "/nodes", xml_data)

        self.assertEquals([], errors)
        node1 = self.model.get_item(cluster_path + "/nodes/node1")
        self.assertEquals("node1", node1.hostname)
        osprofile = self.model.get_item(cluster_path + "/nodes/node1/os")
        self.assertEquals("sample-profile", osprofile.name)
        ip1 = self.model.get_item(cluster_path + "/nodes/node1/network_interfaces/ip1")
        self.assertEquals("nodes", ip1.network_name)

    def test_load_nodes(self):
        cluster_path = "/deployments/dep1/clusters/cluster1"
        self.model.create_item("deployment", "/deployments")
        self.model.create_item("deployment", "/deployments/dep1")
        self.model.create_item("cluster", cluster_path)
        self.model.create_item("os-profile",
                               "/software/profiles/rhel_6_4",
                               name="sample-profile",
                               path="/var", foo="baz")
        self.model.create_item("os-profile2", "/software/profiles/rhel_6_4",
                               name="old_name", path="/var", foo2="old_foo2")
        self.model.create_item("storage-profile-base",
                               "/infrastructure/storage/storage_profiles/profile_1")
        self.model.create_item("system",
                               "/infrastructure/systems/system1",
                               system_name="SYS1")

        xml_data = open(
            os.path.join(os.path.dirname(__file__),
                         "nodes.xml")).read()
        errors = self.loader.load(cluster_path, xml_data)
        self.assertEquals("ItemExistsError", errors[0].error_type)

        nodes = self.model.get_item(cluster_path + "/nodes")
        self.assertEquals(2, len(nodes.children))

        node1 = self.model.get_item(cluster_path + "/nodes/node1")
        self.assertEquals("node1", node1.hostname)
        osprofile = self.model.get_item(cluster_path + "/nodes/node1/os")
        self.assertEquals("sample-profile", osprofile.name)
        ip1 = self.model.get_item(cluster_path + "/nodes/node1/network_interfaces/ip1")
        self.assertEquals("nodes", ip1.network_name)
        sp = self.model.get_item(cluster_path + "/nodes/node1/storage_profile")

    def test_load_node_validation_error(self):
        cluster_path = "/deployments/dep1/clusters/cluster1"
        self.model.create_item("deployment", "/deployments")
        self.model.create_item("deployment", "/deployments/dep1")
        self.model.create_item("cluster", cluster_path)
        xml_data = open(
            os.path.join(os.path.dirname(__file__), "node1_invalid.xml")
        ).read()
        self.assertEquals([
            ValidationError(
                property_name="hostname",
                error_message=(
                    "Invalid value 'node1*INVALID'."
                ),
                item_path="/deployments/dep1/clusters/cluster1/nodes/node1"
            )],
            self.loader.load(cluster_path + "/nodes", xml_data))

    def test_load_root(self):
        self.model.create_item("deployment", "/deployments")
        self.assertFalse(self.model.has_item("/software/profiles/rhel_6_4"))
        xml_data = open(
            os.path.join(os.path.dirname(__file__),
                         "root.xml")).read()
        errors = self.loader.load("/", xml_data, merge=True)
        self.assertEquals([], errors)

        rhel_6_4 = self.model.get_item("/software/profiles/rhel_6_4")
        self.assertEquals("rhel_6_4", rhel_6_4.item_id)
        self.assertEquals("os-profile", rhel_6_4.item_type_id)
        self.assertEquals("sample-profile", rhel_6_4.properties['name'])

        iprange1 = self.model.get_item(
            "/infrastructure/networking/networks/iprange1")
        self.assertEquals("10.10.10.0/24", iprange1.properties['subnet'])

    def test_merge_only_deployments_root(self):
        self.model.create_item("deployment", "/deployments")
        xml_data = self._load_xml_data("root_deployments.xml")
        errors = self.loader.load("/", xml_data, merge=True)
        self.assertEquals([], errors)

        deployment = self.model.get_item("/deployments/site1")

        self.assertEquals(1, len(deployment.children))
        ip1 = self.model.get_item("/deployments/site1/clusters/cluster1/"
                                  "nodes/node1/network_interfaces/ip1")
        self.assertEquals("10.10.10.1", ip1.ipaddress)

    def test_merge_root_into_wrong_path(self):
        self.model.create_item("deployment", "/deployments")
        self.model.create_item("deployment", "/deployments/dep1")
        self.model.create_item("cluster", "/deployments/dep1/clusters/cluster1")
        self.model.create_item(
            "node", "/deployments/dep1/clusters/cluster1/nodes/node1",
            hostname="hostname1")
        xml_data = open(
            os.path.join(os.path.dirname(__file__),
                         "root_deployments.xml")).read()
        errors = self.loader.load("/deployments/dep1/clusters", xml_data, merge=True)
        self.assertEquals(5, len(errors))
        self.assertTrue(isinstance(errors[0], ValidationError))
        self.assertTrue(errors[0].error_type, "InvalidLocationError")

        deployments = self.model.get_item("/deployments")

        self.assertEquals(1, len(deployments.children))
        node1 = self.model.get_item("/deployments/dep1/clusters/cluster1/nodes/node1")
        self.assertEquals("hostname1", node1.hostname)

    def test_merge_link_into_wrong_path(self):
        self.model.create_item("deployment", "/deployments")
        self.model.create_item("deployment", "/deployments/dep1")
        xml_data = open(
            os.path.join(os.path.dirname(__file__),
                         "profiles.xml")).read()
        errors = self.loader.load("/deployments/dep1", xml_data, merge=True)
        self.assertEquals(1, len(errors))
        self.assertTrue(isinstance(errors[0], ValidationError))
        self.assertTrue(errors[0].error_type, "InvalidLocationError")

        deployments = self.model.get_item("/deployments")

        self.assertEquals(1, len(deployments.children))

    def test_link_into_wrong_path(self):
        self.model.create_item("deployment", "/deployments")
        self.model.create_item("deployment", "/deployments/dep1")
        self.model.create_item("cluster", "/deployments/dep1/clusters/cluster1")
        self.model.create_item("node", "/deployments/dep1/clusters/cluster1/nodes/node1", hostname="node1")
        xml_data = open(
            os.path.join(os.path.dirname(__file__),
                         "ip_range_link.xml")).read()
        errors = self.loader.load("/deployments/dep1/clusters/cluster1/nodes/node2/network_interfaces/ip1", xml_data, merge=True)
        self.assertEquals(1, len(errors))
        self.assertTrue(isinstance(errors[0], ValidationError))
        self.assertTrue(errors[0].error_type, "InvalidLocationError")

        ipaddresses = self.model.get_item("/deployments/dep1/clusters/cluster1/nodes/node1/network_interfaces")

        self.assertEquals(0, len(ipaddresses.children))

    def _setup_load_model(self):
        self.model.create_item("deployment", "/deployments")
        self.model.create_item("deployment", "/deployments/dep1")
        self.model.create_item("cluster", "/deployments/dep1/clusters/cluster1")
        self.model.create_item(
            "node", "/deployments/dep1/clusters/cluster1/nodes/node1",
            hostname="hostname1")

    def _setup_load_root_tests(self, fname="root_deployments.xml"):
        self._setup_load_model()
        return open(
            os.path.join(os.path.dirname(__file__),
                         fname)).read()

    def test_load_root_no_merge(self):
        errors = self.loader.load("/", self._setup_load_root_tests(), merge=False)
        self.assertEquals(1, len(errors))
        self.assertTrue(errors[0].error_type, "ItemExistsError")

    def test_load_root_merge(self):
        errors = self.loader.load("/", self._setup_load_root_tests(), merge=True)
        self.assertEquals(0, len(errors))

    def test_load_root_snapshots(self):
        errors = self.loader.load("/", self._setup_load_root_tests("root_with_snapshot.xml"), merge=True)
        self.assertEquals(0, len(errors))

        snapshots = self.model.get_item("/snapshots")
        self.assertEqual(0, len(snapshots.children))

    def test_load_not_updatable_no_existing_item(self):
        errors = self.loader.load("/software/profiles", self._setup_load_root_tests("osprofile2.xml"))
        self.assertEquals(0, len(errors))

        item = self.model.get_item("/software/profiles/rhel_6_2")
        self.assertEquals("sample-profile", item.name)
        self.assertEquals("bar", item.foo)

    def test_load_not_updatable_existing_item(self):
        self.model.create_item("os-profile2", "/software/profiles/rhel_6_2", name="old_name", path="/var", foo="baz")

        errors = self.loader.load("/software/profiles", self._setup_load_root_tests("osprofile2.xml"))
        self.assertEquals(1, len(errors))

    def test_load_not_updatable_merge_no_existing_item(self):
        errors = self.loader.load("/software/profiles", self._setup_load_root_tests("osprofile2.xml"), merge=True)
        self.assertEquals(0, len(errors))

        item = self.model.get_item("/software/profiles/rhel_6_2")
        self.assertEquals("sample-profile", item.name)
        self.assertEquals("bar", item.foo)
        self.assertEquals("Hello", item.misterview())

    def test_load_not_updatable_merge_existing_item(self):
        self.model.create_item("os-profile2", "/software/profiles/rhel_6_2", name="old_name", path="/var", foo="baz")

        errors = self.loader.load("/software/profiles", self._setup_load_root_tests("osprofile2.xml"), merge=True)
        self.assertEquals(0, len(errors))

        item = self.model.get_item("/software/profiles/rhel_6_2")
        self.assertEquals("sample-profile", item.name)
        self.assertEquals("bar", item.foo)
        self.assertEquals("Hello", item.misterview())

    def test_load_not_updatable_replace(self):
        self.model.create_item("os-profile2", "/software/profiles/rhel_6_2", name="old_name", path="/var", foo="baz")
        errors = self.loader.load("/software/profiles", self._setup_load_root_tests("osprofile2.xml"), replace=True)
        self.assertEquals(0, len(errors))

        item = self.model.get_item("/software/profiles/rhel_6_2")
        self.assertEquals("sample-profile", item.name)
        self.assertEquals("Hello", item.misterview())

    def test_load_not_updatable_replace_no_existing_item(self):
        errors = self.loader.load("/software/profiles", self._setup_load_root_tests("osprofile2.xml"), replace=True)
        self.assertEquals(0, len(errors))

        item = self.model.get_item("/software/profiles/rhel_6_2")
        self.assertEquals("sample-profile", item.name)
        self.assertEquals("bar", item.foo)

    def test_load_not_updatable_replace_existing_item(self):
        self.model.create_item("os-profile2", "/software/profiles/rhel_6_2", name="old_name", path="/var", foo="baz")

        errors = self.loader.load("/software/profiles", self._setup_load_root_tests("osprofile2.xml"), replace=True)
        self.assertEquals(0, len(errors))

        item = self.model.get_item("/software/profiles/rhel_6_2")
        self.assertEquals("sample-profile", item.name)
        self.assertEquals("bar", item.foo)

    def _setup_load_replace_tests(self, fname="root_replace.xml"):
        self._setup_load_model()
        return open(
            os.path.join(os.path.dirname(__file__),
                         fname)).read()

    def test_load_replace(self):
        data = self._setup_load_replace_tests()
        errors = self.loader.load("/",  data, replace=True)
        self.assertEquals(0, len(errors))
        self.assertFalse(self.model.has_item("/deployments/dep1"))
        site1 = self.model.get_item("/deployments/site1")
        clusters = site1.children['clusters']
        self.assertEqual(['cluster2'], clusters.children.keys())

    def test_load_replace_invalid_location(self):
        data = self._setup_load_replace_tests(fname="profiles.xml")
        errors = self.loader.load("/deployments", data, replace=True)
        self.assertEquals(1, len(errors))
        self.assertEquals("InvalidLocationError", errors[0].error_type)
        dep1 = self.model.get_item("/deployments/dep1")
        self.assertNotEqual(None, dep1)

    def test_load_snapshots_remain_unchanged(self):
        self.model.create_item("snapshot-base", "/snapshots/snapshot")
        errors = self.loader.load("/", self._setup_load_root_tests("root_with_snapshot.xml"), replace=True)

        self.assertEquals(0, len(errors))

        snapshots = self.model.get_item("/snapshots")
        self.assertEqual(1, len(snapshots.children))
        self.assertEqual("Initial", snapshots.children['snapshot'].get_state())

    def test_load_model_node1(self):
        cluster_path = "/deployments/dep1/clusters/cluster1"
        self.model.create_item("deployment", "/deployments")
        self.model.create_item("deployment", "/deployments/dep1")
        self.model.create_item("cluster", cluster_path)
        self.model.create_item("os-profile2", "/software/profiles/rhel_6_4",
                               name="old_name", path="/var", foo2="old_foo2")
        self.model.create_item("storage-profile-base",
                               "/infrastructure/storage/storage_profiles/profile_1")
        self.model.create_item("system",
                               "/infrastructure/systems/system1",
                               system_name="SYS1")

        self.loader._load_model(
            "/deployments/dep1/clusters/cluster1/nodes",
            self._load_xml_element("node1.xml"))

        self.assertEquals([
            '/deployments/dep1/clusters/cluster1/nodes/node1',
            '/deployments/dep1/clusters/cluster1/nodes/node1/network_interfaces/ip1',
            '/deployments/dep1/clusters/cluster1/nodes/node1/os'],
            self.loader.loaded)

        self.assertEquals("node1", self.model.get_item(
            "/deployments/dep1/clusters/cluster1/nodes/node1").hostname)
        self.assertEquals("sample-profile", self.model.get_item(
            "/deployments/dep1/clusters/cluster1/nodes/node1/os").name)

    def test_load_model_node_collection(self):
        cluster_path = "/deployments/dep1/clusters/cluster1"
        self.model.create_item("deployment", "/deployments")
        self.model.create_item("deployment", "/deployments/dep1")
        self.model.create_item("cluster", cluster_path)
        self.model.create_item("os-profile2", "/software/profiles/rhel_6_4",
                               name="old_name", path="/var", foo2="old_foo2")
        self.model.create_item("storage-profile-base",
                               "/infrastructure/storage/storage_profiles/profile_1")
        self.model.create_item("system",
                               "/infrastructure/systems/system1",
                               system_name="SYS1")

        self.loader._load_model(
            "/deployments/dep1/clusters/cluster1",
            self._load_xml_element("nodes.xml"))

        self.assertEquals([
            '/deployments/dep1/clusters/cluster1/nodes/node1',
            '/deployments/dep1/clusters/cluster1/nodes/node1/network_interfaces/ip1',
            '/deployments/dep1/clusters/cluster1/nodes/node2',
            '/deployments/dep1/clusters/cluster1/nodes/node2/network_interfaces/ip1',
            '/deployments/dep1/clusters/cluster1/nodes/node1/os',
            '/deployments/dep1/clusters/cluster1/nodes/node1/storage_profile',
            '/deployments/dep1/clusters/cluster1/nodes/node1/system',
            '/deployments/dep1/clusters/cluster1/nodes/node2/os',
            '/deployments/dep1/clusters/cluster1/nodes/node2/storage_profile',
            '/deployments/dep1/clusters/cluster1/nodes/node2/system'],
            self.loader.loaded)

        self.assertEquals("node1", self.model.get_item(
            "/deployments/dep1/clusters/cluster1/nodes/node1").hostname)
        self.assertEquals("node2", self.model.get_item(
            "/deployments/dep1/clusters/cluster1/nodes/node2").hostname)

        self.assertEquals("sample-profile", self.model.get_item(
            "/deployments/dep1/clusters/cluster1/nodes/node1/os").name)

    def test_load_model_node1_link(self):
        cluster_path = "/deployments/dep1/clusters/cluster1"
        self.model.create_item("deployment", "/deployments")
        self.model.create_item("deployment", "/deployments/dep1")
        self.model.create_item("cluster", cluster_path)
        self.model.create_item("node", cluster_path + "/nodes/node1",
            hostname="node1")

        self.loader._load_model(
            "/deployments/dep1/clusters/cluster1/nodes/node1/network_interfaces",
            self._load_xml_element("iprange_link.xml"))

        self.assertEquals([
            '/deployments/dep1/clusters/cluster1/nodes/node1/network_interfaces/ip1'],
            self.loader.loaded)

        self.assertEquals("nodes", self.model.get_item(
            "/deployments/dep1/clusters/cluster1/nodes/node1/network_interfaces/ip1"
            ).network_name)

    def test_infrastructure_missing_network(self):
        infrastructure_xml = self._load_xml_data("infrastructure.xml")
        missing_network_xml = self._load_xml_data(
            "infrastructure_missing_network.xml")

        self.loader.load("/", infrastructure_xml, merge=True)
        self.model.set_all_applied()

        self.assertEquals([], self.loader.load("/", missing_network_xml, replace=True))
        self.assertTrue(self.model.has_item('/infrastructure/networking/networks/nodes'))

    def _setup_package(self):
        self.model.register_property_type(
            PropertyType(
                "package_version",
                regex=r'^(latest|[a-zA-Z0-9\._]+)$'
            ))
        self.model.register_property_type(
            PropertyType(
                "package_config",
                regex=r"^(keep|replace)$"
            ))

        self.model.register_item_type(ItemType(
            "package",
            extend_item="software-item",
            name=Property(
                "basic_string",
                required=True,
            ),
            version=Property(
                "package_version",
            ),
            arch=Property(
                "basic_string",
            )))

    def test_properties_replaced(self):
        self._setup_package()
        self.model.create_item("package", "/software/items/telnet", name="telnet", arch="x86")

        telnet_xml = self._load_xml_data("telnet.xml")

        self.model.set_all_applied()

        errs = self.loader.load("/software/items", telnet_xml, replace=True)
        self.assertEquals([], errs)
        telnet = self.model.get_item("/software/items/telnet")
        self.assertEquals({'name': 'telnet'}, telnet.properties)

    def test_properties_merged(self):
        self._setup_package()
        self.model.create_item("package", "/software/items/telnet", name="telnet", arch="x86")

        telnet_xml = self._load_xml_data("telnet.xml")

        self.model.set_all_applied()

        errs = self.loader.load("/software/items", telnet_xml, merge=True)
        self.assertEquals([], errs)
        telnet = self.model.get_item("/software/items/telnet")
        self.assertEquals({'arch': 'x86', 'name': 'telnet'}, telnet.properties)

        telnet_xml = self._load_xml_data("telnet_extra.xml")

        self.model.set_all_applied()

        errs = self.loader.load("/software/items", telnet_xml, merge=True)
        self.assertEquals([], errs)
        telnet = self.model.get_item("/software/items/telnet")
        self.assertEquals({'arch': 'x86',
                           'name': 'telnet2',
                           'version': '1.2'}, telnet.properties)

    def test_properties_merged2(self):
        self.model.create_item("os-profile2", "/software/profiles/rhel_6_2", name="old_name", path="/var", foo2="old_foo2")

        errors = self.loader.load("/software/profiles", self._setup_load_root_tests("osprofile2.xml"), merge=True)
        self.assertEquals(0, len(errors))

        item = self.model.get_item("/software/profiles/rhel_6_2")
        self.assertEquals("sample-profile", item.name)
        self.assertEquals("old_foo2", item.foo2)
        self.assertEquals("foo3", item.foo3)

    def test_properties_replaced2(self):
        self.model.create_item("os-profile2", "/software/profiles/rhel_6_2", name="old_name", path="/var", foo2="old_foo2")

        errors = self.loader.load("/software/profiles", self._setup_load_root_tests("osprofile2.xml"), replace=True)
        self.assertEquals(0, len(errors))

        item = self.model.get_item("/software/profiles/rhel_6_2")
        self.assertEquals("sample-profile", item.name)
        self.assertEquals(None, item.foo2)
        self.assertEquals("foo3", item.foo3)

    def test_duplicate_property_and_item(self):
        self.model.register_item_type(ItemType("some_item",
            extend_item="software-item",
            node=Property("basic_string")
        ))

        self.model.create_item("some_item", "/software/items/some_item",
            node="Hello")

        self.assertEquals("Hello",
            self.model.get_item("/software/items/some_item").node)

        self.assertTrue("node" in self.model.item_types)

        some_item = self._load_xml_data("some_item.xml")
        errs = self.loader.load("/software/items", some_item, replace=True)

        self.assertEquals([], errs)

        self.assertEquals("Hello",
            self.model.get_item("/software/items/some_item").node)

    def test_replace_properties_litpcds_4548(self):
        self.model.register_item_type(ItemType("item",
            extend_item="software-item",
            node=Property("basic_string"),
            name=Property("basic_string"),
            version=Property("basic_string"),
            misterview=View('basic_string', self.mock_view),
        ))

        item = self.model.create_item("item",
                                      "/software/items/item",
                                      node="Node",
                                      name="Name",
                                      version="Version")
        self.model.set_all_applied()
        item = self.model.get_item(item.vpath)
        self.assertEquals("Applied", item.get_state())

        # TC1: Properties are the same as in item - Applied expected
        properties = {
            "node": "Node",
            "name": "Name",
            "version": "Version"}

        errs = self.loader._replace_properties(item.vpath, **properties)
        self.assertEquals("Applied", item.get_state())

        # TC2: Properties are NOT the same as in item - Updated expected
        properties = {"name": "Name"}

        errs = self.loader._replace_properties(item.vpath, **properties)
        item = self.model.get_item(item.vpath)
        self.assertEquals("Updated", item.get_state())

    def test_attempt_to_change_types_in_merge(self):
        self.model.register_item_type(
            ItemType("type_base", extend_item="software-item",
            name=Property("basic_string"),
            version=Property("basic_string"),
        ))
        self.model.register_item_type(
            ItemType("type_a", extend_item="type_base",
            spec_proc=Property("basic_string"),
        ))
        self.model.register_item_type(
            ItemType("type_b", extend_item="type_base",
            spec_proc=Property("basic_string"),
        ))
        item = self.model.create_item("type_a", "/software/items/item",
                                      name="ItemA",
                                      version="1.0")
        xml_data = """<?xml version='1.0' encoding='utf-8'?>
        <litp:type_a  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:litp="http://www.ericsson.com/litp" xsi:schemaLocation="http://www.ericsson.com/litp litp-xml-schema/litp.xsd" id="item">
            <name>ItemA</name>
            <version>1.0</version>
            <spec_proc>special</spec_proc>
        </litp:type_a>"""

        errors = self.loader.load("/software/items", xml_data, merge=True)
        self.assertEquals([], errors)

        xml_data = """<?xml version='1.0' encoding='utf-8'?>
        <litp:type_base  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:litp="http://www.ericsson.com/litp" xsi:schemaLocation="http://www.ericsson.com/litp litp-xml-schema/litp.xsd" id="item">
            <name>ItemA</name>
            <version>1.0</version>
        </litp:type_base>"""

        errors = self.loader.load("/software/items", xml_data, merge=True)
        self.assertEquals(1, len(errors))
        self.assertEquals('Cannot merge from type_a to type_base', errors[0].error_message)

    def test_cascade_delete_path(self):
        cluster1_path = "/deployments/dep1/clusters/cluster1"
        cluster2_path = "/deployments/dep1/clusters/cluster2"
        self.model.create_item("deployment", "/deployments")
        self.model.create_item("deployment", "/deployments/dep1")
        self.model.create_item("cluster", cluster1_path)
        self.model.create_item("cluster", cluster2_path)
        self.model.create_item(
            "node", "/deployments/dep1/clusters/cluster1/nodes/node1",
            hostname="hostname1")
        self.model.create_item(
            "node", "/deployments/dep1/clusters/cluster2/nodes/node1",
            hostname="hostname2")

        self.model.create_item("os-profile2", "/software/profiles/rhel_6_4",
                               name="old_name", path="/var", foo2="old_foo2")
        self.model.create_item("storage-profile-base",
                               "/infrastructure/storage/storage_profiles/profile_1")
        self.model.create_item("system",
                               "/infrastructure/systems/system1",
                               system_name="SYS1")
        self.loader._cascade_delete_path(cluster1_path)
        cluster = self.model.find_modelitem("cluster", {})
        self.assertEquals("cluster2", cluster.item_id)

    def test_create_inherit_from_element(self):
        cluster1_path = "/deployments/dep1/clusters/cluster1"
        self.model.create_item("deployment", "/deployments")
        self.model.create_item("deployment", "/deployments/dep1")
        self.model.create_item("cluster", cluster1_path)
        self.model.create_item(
            "node", "/deployments/dep1/clusters/cluster1/nodes/node1",
            hostname="hostname1")

        self.model.create_item("os-profile2", "/software/profiles/rhel_6_4",
                               name="old_name", path="/var", foo2="old_foo2")
        self.model.create_item("storage-profile-base",
                               "/infrastructure/storage/storage_profiles/profile_1")
        self.model.create_item("system",
                               "/infrastructure/systems/system1",
                               system_name="SYS1")

        self.model.register_item_type(
            ItemType("type_base", extend_item="software-item",
            name=Property("basic_string"),
            version=Property("basic_string"),
        ))
        self.model.register_item_type(
            ItemType("type_a", extend_item="type_base",
            spec_proc=Property("basic_string"),
        ))
        self.model.register_item_type(
            ItemType("type_b", extend_item="type_base",
            spec_proc=Property("basic_string"),
        ))
        item = self.model.create_item("type_a", "/software/items/item",
                                      name="ItemA",
                                      version="1.0")
        item2 = self.model.create_item("type_a", "/software/items/item2",
                                      name="ItemB",
                                      version="1.0")
        xml_data = """<?xml version='1.0' encoding='utf-8'?>
        <litp:type_a-inherit xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:litp="http://www.ericsson.com/litp" xsi:schemaLocation="http://www.ericsson.com/litp litp-xml-schema/litp.xsd" id="item" source_path="/software/items/item"/>"""

        errors = self.loader.load("/ms/items", xml_data, merge=True)
        self.assertEquals([], errors)

        xml_data = """<?xml version='1.0' encoding='utf-8'?>
        <litp:type_a-inherit xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:litp="http://www.ericsson.com/litp" xsi:schemaLocation="http://www.ericsson.com/litp litp-xml-schema/litp.xsd" id="item" source_path="/software/items/item2"/>"""
        errors = self.loader.load("/ms/items", xml_data, merge=True)
        self.assertEquals(1, len(errors))
        self.assertEquals('Cannot update source path "/software/items/item2". type_a "item" is already inherited from "/software/items/item"', errors[0].error_message)
        self.assertEquals('/ms/items/item', errors[0].item_path)
        self.assertEquals('ValidationError', errors[0].error_type)

        xml_data = """<?xml version='1.0' encoding='utf-8'?>
        <litp:type_b  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:litp="http://www.ericsson.com/litp" xsi:schemaLocation="http://www.ericsson.com/litp litp-xml-schema/litp.xsd" id="item">
            <name>ItemB</name>
            <version>1.0</version>
        </litp:type_b>"""

        errors = self.loader.load("/software/items", xml_data, merge=True)
        self.assertEquals('Cannot merge from type_a to type_b', errors[0].error_message)

        xml_data = """<?xml version='1.0' encoding='utf-8'?>
        <litp:type_base-inherit xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:litp="http://www.ericsson.com/litp" xsi:schemaLocation="http://www.ericsson.com/litp litp-xml-schema/litp.xsd" id="item" source_path="/software/items/item"/>"""

        errors = self.loader.load("/ms/items", xml_data, merge=True)
        self.assertEquals(2, len(errors))
        self.assertEquals('Cannot merge from type_a to type_base-inherit', errors[0].error_message)
        self.assertEquals('An inherited item is not allowed to reference a source item of type "type_b" using item type "type_base"', errors[1].error_message)

        xml_data = """<?xml version='1.0' encoding='utf-8'?>
        <litp:type_a-inherit xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:litp="http://www.ericsson.com/litp" xsi:schemaLocation="http://www.ericsson.com/litp litp-xml-schema/litp.xsd" id="item_x" source_path="/source/item/does/not/exist"/>"""
        errors = self.loader.load("/ms/items", xml_data, replace=True)
        self.assertEquals(1, len(errors))
        self.assertEquals(
                "Source item /source/item/does/not/exist doesn't exist",
                errors[0].error_message)

    def test_element_equals_item(self):

        self.model.register_item_type(ItemType(
            "package",
            extend_item="software-item",
            name=Property(
                "basic_string",
                required=True,
            ),
        ))


        self.model.register_item_type(
            ItemType("type_base", extend_item="software-item",
            name=Property("basic_string"),
            version=Property("basic_string"),
            packages=Collection("package")
        ))

        self.model.create_item("type_base", "/software/items/item",
                                      name="ItemBase",
                                      version="1.0")

        self.model.create_item("package", "/software/items/item/packages/pkg1",
                                      name="Package1")

        item = self.model.get_item("/software/items/item/packages")

        xml_data = """<?xml version='1.0' encoding='utf-8'?>
        <litp:type_base-packages-collection xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:litp="http://www.ericsson.com/litp" xsi:schemaLocation="http://www.ericsson.com/litp litp-xml-schema/litp.xsd" id="packages">
            <package id="pkg1">
                <name>Package1</name>
            </package>
        </litp:type_base-packages-collection>"""

        element = etree.fromstring(xml_data)
        self.assertEquals(True, self.loader._element_equals_item(element, item))

        item = self.model.get_item("/software/items/item/packages/pkg1")
        self.assertEquals(False, self.loader._element_equals_item(element, item))

        xml_data = """<?xml version='1.0' encoding='utf-8'?>
        <litp:type_base  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:litp="http://www.ericsson.com/litp" xsi:schemaLocation="http://www.ericsson.com/litp litp-xml-schema/litp.xsd" id="item">
            <name>ItemA</name>
            <version>1.0</version>
            <litp:type_base-packages-collection>
                <package>
                    <name>Package1</name>
                </package>
            </litp:type_base-packages-collection>
        </litp:type_base>"""

        item = self.model.get_item("/software/items/item")
        element = etree.fromstring(xml_data)
        self.assertEquals(True, self.loader._element_equals_item(element, item))

    def test_validate_unique_items(self):
        xml_data = """<?xml version='1.0' encoding='utf-8'?>
    <litp:software xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:litp="http://www.ericsson.com/litp" xsi:schemaLocation="http://www.ericsson.com/litp litp-xml-schema/litp.xsd" id="software">
    <litp:software-deployables-collection id="deployables"/>
    <litp:software-items-collection id="items">
        <litp:package id="pkg1">
        <name>foo</name>
        </litp:package>
        <litp:package id="pkg1">
        <name>bar</name>
        </litp:package>
    </litp:software-items-collection>
    </litp:software>"""

        element = etree.fromstring(xml_data)
        errs = self.loader._validate_unique_items("/", element)
        self.assertEquals(1, len(errs))
        self.assertEquals("InvalidXMLError" , errs[0].error_type)

    def test_double_inherit_sort_order(self):
        xml_data = self._load_xml_data("double_inherit.xml")
        errs = self.loader.load("/", xml_data, merge=True)
        self.assertTrue(len(errs) == 0)

    def test_recheck_inherits(self):
        self.model.register_item_type(
            ItemType("package", extend_item="software-item",
            name=Property("basic_string"),
        ))
        self.model.create_item("package", "/software/items/package1",
                               name="package1")
        self.model.create_inherited("/software/items/package1", "/ms/items/package1",
                                    name="package1")
        parent_element = etree.fromstring("""
            <litp:package-inherit
                xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                xmlns:litp="http://www.ericsson.com/litp"
                xsi:schemaLocation="http://www.ericsson.com/litp litp-xml-schema/litp.xsd"
                source_path="/software/items/package1"
                id="package1"/>
        """)
        self.loader._inherits = {'/ms/items/package1': parent_element}
        remove_list = ['/software/items/package1']
        errs = self.loader._recheck_inherits(remove_list)
        self.assertEquals(1, len(errs))
