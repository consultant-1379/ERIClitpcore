import os
import unittest
import mock
from mock import patch
from litp.core.model_type import (
    ItemType,
    PropertyType,
    Collection,
    Reference,
    Property
)
from litp.core.packages_import import (
    ModelProxy,
    PackagesImport,
    DestinationPath,
    SourcePath,
)
from litp.core.iso_import import RepoPathChecker
from litp.core.model_manager import ModelManager
from tempfile import gettempdir


class PackagesImportTest(unittest.TestCase):
    def setUp(self):
        self.model = ModelManager()
        self.model.register_property_type(PropertyType("basic_string"))

        self.model.register_item_type(
            ItemType(
                "root",
                nodes=Collection("node"),
                profiles=Collection("os-profile"),
                systems=Collection("system"),
                graph=Collection("graph_node"),
            )
        )
        self.model.register_item_type(
            ItemType(
                "node",
                hostname=Property("basic_string"),
                system=Reference("system"),
                os=Reference("os-profile", require="system")
            )
        )
        self.model.register_item_type(
            ItemType(
                "system",
                uid=Property("basic_string"),
                disks=Collection("disk")
            )
        )
        self.model.register_item_type(
            ItemType(
                "disk",
                mount=Property("basic_string"),
            )
        )
        self.model.register_item_type(
            ItemType(
                "os-profile",
                name=Property("basic_string"),
                path=Property("basic_string"),
                items=Collection("package")
            )
        )
        self.model.register_item_type(
            ItemType(
                "package",
                name=Property("basic_string"),
            )
        )
        self.model.register_item_type(
            ItemType(
                "graph_node",
                dest=Reference("graph_node"),
                uid=Property("basic_string")
            )
        )

        self.model.create_root_item("root")
        self.node1 = self.model.create_item(
            "node",
            "/nodes/node1",
            hostname="node1"
        )
        self.os1 = self.model.create_item(
            "os-profile",
            "/profiles/os1",
            name="rhel",
            path="/var/www/html/rhel"
        )
        self.os2= self.model.create_item(
            "os-profile",
            "/profiles/os2",
            name="coolos",
            path="/var/www/html/coolos"
        )
        self.vim = self.model.create_item(
            "package",
            "/profiles/os1/items/vim",
            name="vim"
        )
        self.sys1 = self.model.create_item(
            "system",
            "/systems/sys1",
            uid="sys1"
        )
        self.d1 = self.model.create_item(
            "disk",
            "/systems/sys1/disks/d1",
            mount="/my/disk"
        )

        self.model.create_inherited(
            "/profiles/os1",
            "/nodes/node1/os",
        )
        self.model.create_inherited(
            "/systems/sys1",
            "/nodes/node1/system",
        )

        self.node = self.model.query("node")[0]
        self.ms = "ms1"
        self.tempdir = gettempdir()

    def _mock_func(self, *args):
        pass

    @property
    def _bad_paths(self):
        return ["ed", "12212", "C:"]

    def test_source_path_validator(self):
        source_paths = self._bad_paths

        for path in source_paths:
            p = SourcePath(path)
            self.assertEqual(
                p.is_valid(),
                False
            )

    def test_bad_destination_path_validator(self):
        destination_paths = self._bad_paths

        for path in destination_paths:
            p = DestinationPath(path)
            self.assertEqual(
                p.is_valid(),
                False

            )

    def test_good_destination_path_validator(self):
        destination_path = self.tempdir

        p = DestinationPath(destination_path)

        self.assertTrue(p.is_valid())

    def test_repo_path_checker(self):
        checker = RepoPathChecker(self.model)
        self.assertEqual(
            checker.check_path("/var/www/html/coolos"),
            "/profiles/os2")
        self.assertEqual(
            checker.check_path("/var/www/html/not/a/profile"),
            None)
        checker = RepoPathChecker()
        self.assertEqual(
            checker.check_path("/var/www/html/coolos"),
            None)
        self.assertEqual(
            checker.check_path("/var/www/html/not/a/profile"),
            None)

    def test_clashing_destination_path_validator(self):
        destination_path = "/var/www/html/coolos"

        p = DestinationPath(destination_path,
                            RepoPathChecker(self.model))

        self.assertFalse(p.is_valid())

    def test_repr(self):

        source_path = SourcePath("/tmp")
        self.assertEquals("<Path - /tmp/ >", repr(source_path))

        destination_path = DestinationPath("/tmp")
        self.assertEquals("<Path - /tmp >", repr(destination_path))

    def test_model_proxy(self):
        proxy = ModelProxy(self.model)
        self.assertEqual([], proxy.get_all_nodes())
        self.assertEqual([], proxy._ms_nodes())

    def test_3pp_import(self):
        source_path = SourcePath("/tmp/")
        destination_path = DestinationPath("3pp_rhel7")

        packages_import = PackagesImport(
            source_path,
            destination_path,
            mock.MagicMock()
        )

        self.assertEquals(
            "<PackagesImport - /tmp/ - /var/www/html/3pp_rhel7/ >",
            repr(packages_import)
        )

    @patch('litp.core.packages_import.os.path.exists')
    @patch('litp.core.packages_import.os.makedirs')
    @patch('litp.core.packages_import.os.walk')
    def test_is_modules_in_appstream(self, mock_walk, mock_dir, mock_exists):
        source_path = SourcePath \
                ("/tmp/RHEL8.8_AppStream-1.0.8/Packages/123-modules.yaml.gz")
        destination_path = DestinationPath \
                    ("/var/www/html/8.8/updates_AppStream/x86_64/Packages")

        packages_import = PackagesImport(
            source_path,
            destination_path,
            mock.MagicMock()
        )

        mock_exists.return_value = False
        mock_walk.return_value = \
            [('/tmp/RHEL8.8_AppStream-1.0.8', ['Packages'], \
            ['123-modules.yaml.gz', '123-comps.xml'])]

        self.assertTrue(packages_import._is_modules_in_appstream())
        mock_dir.assert_called()

        mock_walk.return_value = \
            [('/tmp/RHEL8.8_AppStream-1.0.8', ['Packages'], \
            ['123-comps.xml'])]
        self.assertFalse(packages_import._is_modules_in_appstream())

    def test_is_src_appstream(self):
        appstream_paths = ['8.8_AppStream-1.0.2', '10.89_AppStream-16.8.4', \
                           '8.10_AppStream-116.243.832', '89.93_AppStream-11.2.22']
        destination_path = DestinationPath \
                    ("/var/www/html/8.8/updates_AppStream/x86_64/Packages")

        for src_path in appstream_paths:
            source_path = SourcePath("/tmp/RHEL{0}/Packages".format(src_path))
            packages_import = PackagesImport(
                source_path,
                destination_path,
                mock.MagicMock()
            )
            self.assertTrue(packages_import._is_src_appstream())

    def test_src_not_appstream(self):
        appstream_paths = ['861.8_AppStream-21.0.2', '.89_appStream-1.8.4', \
                           '_AppStream', '8.13_Appstream-11.2.223']
        destination_path = DestinationPath \
                    ("/var/www/html/8.8/updates_AppStream/x86_64/Packages")

        for src_path in appstream_paths:
            source_path = SourcePath("/tmp/RHEL{0}/Packages".format(src_path))
            packages_import = PackagesImport(
                source_path,
                destination_path,
                mock.MagicMock()
            )
            self.assertFalse(packages_import._is_src_appstream())

    def test_packages_import(self):

        source_path = SourcePath("/tmp/")
        destination_path = DestinationPath("os")

        packages_import = PackagesImport(
            source_path,
            destination_path,
            mock.MagicMock()
        )

        self.assertEquals(
            "<PackagesImport - /tmp/ - /var/www/html/7/os/x86_64/Packages >",
            repr(packages_import)
        )

    def test_get_all_nodes(self):
        self.node2 = self.model.create_item(
                                    "node", "/nodes/node2", hostname="node2"
                                            )
        self.node3 = self.model.create_item(
                                    "node", "/nodes/node3", hostname="node3"
                                            )
        self.node4 = self.model.create_item(
                                    "node", "/nodes/node4", hostname="node4"
                                            )
        proxy = ModelProxy(self.model)
        self.node1.set_initial()
        self.node2.set_applied()
        self.node3.set_updated()
        self.node4.set_for_removal()
        # nodes in initial state should not appear, neither should the node in
        # the ForRemoval state
        expected = set(['node3', 'node2'])
        nodes = proxy.get_all_nodes()
        self.assertEquals(len(expected), len(nodes))
        self.assertEquals(expected, set(nodes))
