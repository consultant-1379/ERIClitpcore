##############################################################################
# COPYRIGHT Ericsson AB 2013
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################

from unittest import TestCase
from mock import MagicMock, Mock, patch
import socket

from litp.extensions.core_extension import CoreExtension, MSValidator
from litp.core.validators import ValidationError
from litp.core.exceptions import ViewError
from litp.core.model_manager import ModelManager, ModelItem
from litp.core.model_type import ItemType, Property, Child


class CoreExtensionsTest(TestCase):
    def setUp(self):
        self.extension = CoreExtension()

    def test_MSValidator(self):
        ms_validator = MSValidator()
        old_gethostname = socket.gethostname
        properties = {'hostname': 'ut_expected_value'}
        socket.gethostname = MagicMock(return_value="ut_expected_value")
        a = ms_validator.validate(properties)
        self.assertEquals(ms_validator.validate(properties), None)

        properties = {'hostname': 'ut_not_expected_value'}

        socket.gethostname = MagicMock(return_value="ut_expected_value")

        self.assertTrue(isinstance(ms_validator.validate(properties), ValidationError))

        socket.gethostname = old_gethostname

    def test_physical_device_name_view_error(self):
        node = MagicMock(is_initial=lambda: True)
        # if no physical devices are found the view should throw an exception
        node.storage_profile.query.return_value = []
        disk = MagicMock()
        disk.get_node.return_value = node
        self.assertRaises(ViewError, CoreExtension.gen_disk_fact_name, MagicMock(), disk)

    def test_physical_device_name(self):
        manager = MagicMock()
        physical_device = MagicMock()
        node = MagicMock(is_initial=lambda: True)
        node.storage_profile.query.return_value = [physical_device]
        node.storage_profile.view_root_vg = 'imroot'

        # is_root_vg = False
        physical_device.parent.parent.volume_group_name = 'notroot'
        disk = MagicMock()
        disk.uuid = '123'
        disk.name = 'bar'
        disk.bootable = 'false'
        disk.get_node.return_value = node
        self.assertEquals(r'$::disk_123_dev',
                          CoreExtension.gen_disk_fact_name(manager, disk))

        # is_root_vg = True
        physical_device.parent.parent.volume_group_name = 'imroot'
        disk = MagicMock()
        disk.uuid = '456'
        disk.name = 'bar'
        disk.bootable = 'false'
        disk.disk_part = 'true'
        disk.get_node.return_value = node
        self.assertEquals(r'$::disk_456_part1_dev',
                          CoreExtension.gen_disk_fact_name(manager, disk))

        disk = MagicMock()
        disk.uuid = '789-45'
        disk.name = 'bar'
        disk.bootable = 'false'
        disk.disk_part = 'false'
        node = MagicMock(is_initial=lambda: False)
        disk.get_node.return_value = node
        self.assertEquals(r'$::disk_789_45_dev',
                          CoreExtension.gen_disk_fact_name(manager, disk))

    @patch('litp.extensions.core_extension.CoreExtension._parent_cluster')
    def test_resolve_clustered_service_nodes(self, parent_cluster):
        n1 = Mock(item_id="node1")
        n2 = Mock(item_id="node2")
        n3 = Mock(item_id="node3")
        n4 = Mock(item_id="node4")
        n5 = Mock(item_id="node5")
        cluster = Mock()
        cluster.nodes = [n2, n3, n1, n5, n4]
        parent_cluster.return_value = cluster

        service = Mock(node_list="node2,node1")
        nodes = self.extension.resolve_clustered_service_nodes(None,
                                                               service)
        self.assertEqual(nodes, [n2, n1])

        service = Mock(node_list="node5,node2,node1,node3")
        nodes = self.extension.resolve_clustered_service_nodes(None,
                                                               service)
        self.assertEqual(nodes, [n5, n2, n1, n3])

    def test_comma_separated_alias_names_torf_152052(self):
        '''
        The regular expression is expected to be constructed like this:

        single_alphanum = r"[a-zA-Z0-9]"
        single_alphanum_and_hyphen = r"[a-zA-Z0-9\-]"
        optional_alphanums_and_hyphens = single_alphanum_and_hyphen + r"*"
        dot = r"\."
        main_token = r"(" + single_alphanum + r"|" + single_alphanum + optional_alphanums_and_hyphens + single_alphanum + r")"
        csl_element = main_token + r"(" + dot + main_token + r")*"
        regular_expression = r"^" + csl_element + r"(," + csl_element + r")*$"
        '''

        def run_test_with_data(dataset, error_expected):
            mock_item_path = "/test_item"
            for value in dataset:

                response = manager.create_item("mock_152052",
                                               mock_item_path,
                                               alias_names=value)

                if error_expected:
                    self.assertTrue(isinstance(response, list))
                    self.assertEqual(response,
                                     [ValidationError(property_name='alias_names',
                                                      error_message="Invalid value '%s'." % value)])
                else:
                    self.assertTrue(isinstance(response, ModelItem))

                    # Cleanup for next test
                    manager.remove_item(mock_item_path)

        manager = ModelManager()
        manager.register_property_types(self.extension.define_property_types())

        mock_itemtype = ItemType("mock_152052",
                                 alias_names=Property("comma_separated_alias_names",   # The property-type under test
                                                      required=True,
                                                      prop_description="Comma separated list of alias names"))

        root_itemtype = ItemType("root",
                                 test_item=Child(mock_itemtype.item_type_id))
        manager.register_item_type(root_itemtype)
        manager.create_root_item(root_itemtype.item_type_id)
        manager.register_item_type(mock_itemtype)

        dataset1 = ['alias',
                    'alias.2',
                    'alias,alias.2',
                    'alias.2,alias',
                    'alias,alias',
                    'alias.2,alias.3,alias',
                    'alias.2,alias,alias.3',
                    'alias.2,alias.3,alias.4',
                    'alias.2,al--s.3,alias.4',
                    'al--s.2,alias.3,alias.4',
                    'alias.2,alias.3,a---s.4',
                    'alias.2,alias.3333,alias.4ffqwefqwef',
                    'alias.alias',
                    'alias.alias.alias',
                    'a-ias',
                    'a-ias.alias2',
                    'a-ias.a-ias2',
                    'a-ias.a------ias2',
                    'a.b.c.d.e.f.g.h.i.j.k.l.m.n.o.p.q.r.s.t.u.v.w.x.y.z']

        dataset2 = ['alias-',
                    '-lias',
                    'alias.-alias.alias',
                    'alias.alias.alias-',
                    'alias..alias',
                    'alias,alias.alias-',
                    'alias.alias-,alias']

        run_test_with_data(dataset1, False)
        run_test_with_data(dataset2, True)
