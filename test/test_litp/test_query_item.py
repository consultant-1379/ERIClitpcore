 # -*- coding: utf-8 -*-
import unittest
import mock
from litp.core.model_manager import QueryItem
from litp.core.model_manager import ModelManager
from litp.core.model_type import PropertyType
from litp.core.model_type import ItemType
from litp.core.model_type import Property
from litp.core.model_type import Child

from itertools import chain
from litp.core.model_manager import ModelManagerException
from litp.core.model_type import Collection
from litp.core.model_type import RefCollection
from litp.core.model_type import Reference
from litp.core.model_item import ModelItem
from litp.core.model_item import CollectionItem, RefCollectionItem
from litp.core.validators import IsNotDigitValidator,IntRangeValidator

# helper functions
def get_vpath(item):
    return item.get_vpath()

def vpath_sort(items):
    return sorted(items, key=lambda item: item.get_vpath())

def flatten(list_of_iter):
    return list(chain.from_iterable(list_of_iter))

def print_dict(some_dict, title=None):
    if title:
        print '\n[%s]' % title
    for key,value in sorted(some_dict.items()):
        print key, sorted(value)

def print_vpaths(some_list, title=None):
    if title:
        print '\n[%s]' % title
    for item in some_list:
        print item.get_vpath()

# helper function to show where dict comparsions fail
def dict_diff(expected, result):
    diff = {}
    for x in result:
        if x not in expected or result[x] != expected[x]:
            diff[x] = result[x]
    return diff

def match_vpath(items, vpath):
    for x in items:
        if x.get_vpath() == vpath:
            return x
    return None

def list_diff(expected, result):
    diff = []
    for item in result:
        vpath = item.get_vpath()
        match = match_vpath(expected, vpath)
        if match is None:
            diff.append(item)
    return diff

def match_qitem(x,y):
    if id(x) == id(y):
        return True
    if not isinstance(x, QueryItem):
        return False
    if not isinstance(y, QueryItem):
        return False
    if x._model_item != y._model_item:
        return False
    if x.vpath != y.vpath:
        return False
    return True

def match_qitems(xlist, ylist):
    if len(xlist) != len(ylist):
        return False
    for x,y in zip(vpath_sort(xlist), vpath_sort(ylist)):
        if not match_qitem(x, y):
            return False
    return True


def is_undefined(qitem):
    return not any([
        qitem.is_initial() or
        qitem.is_applied() or
        qitem.is_updated() or
        qitem.is_removed() or
        qitem.is_for_removal()
    ])


class QueryItemTest(unittest.TestCase):
    """Class tests behaviour of QueryItem"""

    def setUp(self):
        self.model_manager = mock.Mock(
            'litp.core.model_manager.ModelManager', autospec=True)

    def test_repr_no_model_item(self):
        self.model_manager.get_item = mock.Mock(return_value=None)
        qi = QueryItem(self.model_manager, "/foo")
        try:
            str(qi)
        except AttributeError:
            self.fail()

    def test_equality_comparison_hash(self):
        model = ModelManager()
        model.register_property_type(PropertyType("basic_string"))
        model.register_item_types([
            ItemType("foo1"),
            ItemType("foo2"),
            ItemType(
                "root",
                foo1=Child("foo1"),
                foo2=Child("foo2")
            )
        ])
        model.create_root_item("root")
        model.create_item("foo1", "/foo1")
        model.create_item("foo2", "/foo2")

        mitem1 = model.get_item("/foo1")
        mitem2 = model.get_item("/foo2")

        # test positive
        qitem1 = QueryItem(model, mitem1)
        qitem2 = QueryItem(model, mitem1)
        self.assertEqual(qitem1, qitem2)
        self.assertEqual(0, cmp(qitem1, qitem2))
        self.assertEqual(hash(qitem1), hash(qitem2))

        # test negative
        qitem1 = QueryItem(model, mitem1)
        qitem2 = QueryItem(model, mitem2)
        self.assertNotEqual(qitem1, qitem2)
        self.assertNotEqual(hash(qitem1), hash(qitem2))

        # test nonequal comparison
        self.assertEqual(-1, cmp(qitem1, qitem2))
        self.assertEqual(1, cmp(qitem2, qitem1))

    def test_property_update(self):
        model = ModelManager()
        model.register_property_type(PropertyType("basic_string"))
        model.register_item_type(
            ItemType(
                "foo2",
                baz=Property("basic_string", updatable_plugin=True),
            )
        )
        model.register_item_type(
            ItemType(
                "foo",
                bar=Property("basic_string"),
                baz=Property("basic_string", updatable_plugin=True),
                foo2=Child("foo2")
            )
        )
        model.register_item_type(
            ItemType(
                "root",
                foo=Child("foo"),
            )
        )
        model.create_root_item("root")
        model.create_item("foo", "/foo", bar="foobar")
        model.create_item("foo2", "/foo/foo2")

        item = QueryItem(model, model.query("foo")[0])

        new_value = "something_different"
        old_state = item.get_state()

        self.assertRaises(AttributeError, item.__setattr__, "bar", new_value)
        self.assertRaises(AttributeError, item.__setattr__, "baz", new_value)

        item = QueryItem(model, model.query("foo")[0], updatable=True)

        self.assertRaises(AttributeError, item.__setattr__, "bar", new_value)
        item.baz = new_value
        self.assertEquals(new_value, item.baz)
        self.assertEquals(old_state, item.get_state())

        item = model.query("foo")[0]
        self.assertEquals(new_value, item.baz)
        self.assertEquals(old_state, item.get_state())

        item = QueryItem(model, model.query("foo")[0], updatable=True)
        item.foo2.baz = new_value
        self.assertEquals(new_value, item.foo2.baz)


class QueryItemTestCase(unittest.TestCase):

    # QueryItem:
    # In the fields of hell where the grass grows high
    # Are the graves of dreams allowed to die.
    # -- Richard Harter

    def setup_common(self):
        self.model = ModelManager()
        self.query = self._query
        self.query_by_vpath = self._query_by_vpath
        self.errors = []

    def create(self, item_type, item_path, **props):
        result = self.model.create_item(item_type, item_path, **props)
        if not isinstance(result, ModelItem):
            self.errors.extend(result)
        return result

    def _query(self, *args, **kwargs):
        model_items = self.model.query(*args, **kwargs)
        query_items = [QueryItem(self.model, model_item)
                for model_item in model_items]
        return query_items

    def _query_by_vpath(self, *args, **kwargs):
        model_item = self.model.query_by_vpath(*args, **kwargs)
        query_item = QueryItem(self.model, model_item)
        return query_item

    def update(self, item_path, **props):
        result = self.model.update_item(item_path, **props)
        if not isinstance(result, ModelItem):
            self.errors.extend(result)
        return result

    def inherit(self, source_item_path, item_path, **props):
        result = self.model.create_inherited(source_item_path, item_path,
                                           **props)
        if not isinstance(result, ModelItem):
            self.errors.extend(result)
        return result

    def get(self, item_path):
        return self.model.get_item(item_path)

    def remove(self, item_path):
        return self.model.remove_item(item_path)

    def query_single(self, *args, **kwargs):
        qitems = self.query(*args, **kwargs)
        if len(qitems) > 1:
            raise ValueError('list length > 1')
        return qitems[0] if qitems else None

    def make_query_items(self, *model_items):
        qitems = []
        for item in model_items:
            qitems.append(
                QueryItem(self.model, item)
            )
        return qitems

    def query_model(self,root_query,sub_query):
        results = []
        root_qitems = self.query(root_query)
        for root_qitem in root_qitems:
            sub_qitems = root_qitem.query(sub_query)
            results.append(sub_qitems)
        return results

    def extract_items(self, qitems):
        return [ qitem._model_item for qitem in qitems ]


class TwoNodeMixIn(object):

    def register_types(self):
        self.model.register_property_types([
            PropertyType("any_string", regex=r"^.*$"),
            PropertyType("basic_string", regex=r"^[a-zA-Z0-9\-\._]+$"),
            PropertyType("basic_boolean", regex=r"^(true|false)$"),
            PropertyType("digit", regex=r"^[0-9]$"),
            PropertyType("integer", regex=r"^[0-9]+$"),
            PropertyType("os_version", regex=r"^rhel6$"),
            PropertyType( "package_version",
                regex=r'^(latest|[a-zA-Z0-9\._]+)$'),
            PropertyType("disk_uuid",
                regex=r"^[a-zA-Z0-9_][a-zA-Z0-9_-]*$"),
            PropertyType("disk_size", regex=r"^[1-9][0-9]{0,}[MGT]$"),
            PropertyType("mac_address",
                         regex=r"^([a-fA-F0-9]{2}(:)){5}([a-fA-F0-9]{2})$"),
            PropertyType("hostname",
                         regex=r"^(\.[a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9\-]"\
                         "{0,61}[a-zA-Z0-9])$",
                         validators=[IsNotDigitValidator()]),
            PropertyType('node_id', validators=[
                IntRangeValidator(min_value=1, max_value=2047)]),
            PropertyType("file_path_string",
                         regex=r"^[A-Za-z0-9\-\._/#:\s*]+$"),
            PropertyType(
                "package_config",
                regex=r"^(keep|replace)$"
            ),
            PropertyType(
                'fs_mount_point',
                regex='^(swap|(/[a-zA-Z0-9_/-]*))$'
            ),
            PropertyType(
                'fs_type',
                regex='^(ext4|swap)$'
            ),
            PropertyType(
                'fs_size',
                regex='^[1-9][0-9]{0,}[MGT]$'
            ),
            PropertyType(
                'disk_id',
                regex='^[^,-]+$'
            ),
            PropertyType(
                'vol_group',
                regex='^([a-zA-Z0-9_/][a-zA-Z0-9_/-]*)$'
            ),
            PropertyType(
                'vol_driver',
                regex='^(lvm|vxvm)$'
            )
        ])

        self.model.register_item_types([
            ItemType(
                "root",
                item_description="root item for /.",
                ms=Child("ms", required=True),
                software=Child("software", required=True),
                infrastructure=Child("infrastructure", required=True),
                deployments=Collection("deployment"),
            ),
            ItemType(
                "ms",
                item_description="Management Server.",
                hostname=Property(
                    "hostname",
                    prop_description="hostname for this node.",
                    required=True,
                    default="ms1"
                ),
                os=Reference("os-profile", require="system"),
                system=Reference("system"),
                items=RefCollection("software-item"),
            ),
            ItemType(
                "software",
                item_description="/software root item contains software.",
                profiles=Collection("profile"),
                items=Collection("software-item"),
            ),
            ItemType(
                "profile",
                item_description="Base profile item.",
            ),
            ItemType(
                "os-profile",
                extend_item="profile",
                item_description="OS profile for a node.",
                name=Property(
                    "basic_string",
                    required=True,
                    prop_description="Name of profile."
                ),
                arch=Property(
                    "basic_string",
                    required=True,
                    default="x86_64",
                    prop_description="Architecture of OS."
                ),
                breed=Property(
                    "basic_string",
                    required=True,
                    default="redhat",
                    prop_description="Breedtecture of OS."
                ),
                version=Property(
                    "os_version",
                    required=True,
                    default="rhel6",
                    prop_description="Version of OS profile."
                ),
                path=Property(
                    "file_path_string",
                    required=True,
                    prop_description="Path to OS image."
                ),
            ),
            ItemType(
                "software-item",
                item_description="software item.",
            ),
            ItemType(
                "infrastructure",
                item_description="/infrastructure root item contains infrastructure items.",
                systems=Collection("system"),
                storage=Child("storage", required=True)
            ),
            ItemType(
                "system",
                item_description="Base system item.",
                serial=Property(
                    "basic_string",
                    prop_description="Serial number of system."
                ),
                system_name=Property(
                    "basic_string",
                    prop_description="Name of system.",
                    required=True
                ),
                disks=Collection("disk"),
                network_interfaces=Collection("nic"),
            ),
            ItemType(
                "disk",
                item_description="Base disk item",
                bootable=Property("basic_boolean", default="false"),
                name=Property(
                    "basic_string",
                    prop_description="Name of this disk.",
                    required=True,
                ),
                size=Property(
                    "disk_size",
                    required=True,
                    prop_description="Size of this disk.",
                ),
                uuid=Property(
                    "disk_uuid",
                    prop_description="UUID of this disk.",
                    required=True,
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
                    required=True,
                    prop_description="Interface name for the NIC"
                ),
            ),
            ItemType(
                "storage",
                item_description="Storage configuration.",
                storage_profiles=Collection("storage-profile-base"),
            ),
            ItemType(
                'storage-profile-base',
                item_description="A description of volume groups "
                "and file systems that live on them.",
                storage_profile_name=Property(
                    'basic_string',
                    prop_description="Name of storage profile."
                ),
            ),
            ItemType(
                'file-system',
                item_description='A file-system.',
                type=Property(
                    'fs_type',
                    prop_description='File-System Type.',
                    required=True,
                    default='ext4'
                ),
                size=Property(
                    'fs_size',
                    prop_description='File-System Size.',
                    required=True
                ),
                mount_point=Property(
                    'fs_mount_point',
                    prop_description='File-System Mount Point.',
                    required=True
                )
            ),
            ItemType(
                'physical-device',
                item_description='A physical-device.',
                device_name=Property(
                    'disk_id',
                    prop_description='Identifier of Physical-Device Item.',
                    required=True
                )
            ),
            ItemType(
                'volume-group',
                item_description='A storage volume-group.',
                volume_group_name=Property(
                    'vol_group',
                    prop_description='Name of Volume-Group Item.',
                    required=True
                ),
                file_systems=Collection(
                    'file-system',
                    min_count=1, max_count=5
                ),
                physical_devices=Collection(
                    'physical-device',
                    min_count=1, max_count=1
                ),
                volume_driver=Property(
                    'vol_driver',
                    prop_description='Logical volume managment driver. ' +
                             'Must be one of ``vxvm`` and ``lvm``.',
                    required=True,
                    default='lvm'
                )
            ),
            ItemType('storage-profile',
                item_description='A storage-profile.',
                extend_item='storage-profile-base',
                volume_groups=Collection(
                    'volume-group',
                    min_count=1, max_count=255),
            ),
            ItemType(
                'deployment',
                item_description='A deployment.',
                clusters=Collection('cluster', min_count=1, max_count=50),
            ),
            ItemType(
                "cluster",
                item_description="A cluster of nodes.",
                nodes=Collection("node", min_count=1, max_count=50),
                software=RefCollection("software-item", require="nodes"),
            ),
            ItemType(
                "node",
                item_description="A single Compute Node.",
                hostname=Property(
                    "hostname",
                    required=True,
                    prop_description="hostname for this node.",
                ),
                os=Reference(
                    "os-profile",
                    require="system",
                    required=True
                ),
                system=Reference(
                    "system",
                    required=True,
                    exclusive=True
                ),
                items=RefCollection("software-item", require="os"),
                storage_profile=Reference(
                    "storage-profile-base",
                    require="os",
                    required=True
                ),
                node_id=Property(
                    "node_id",
                )
            ),
            ItemType(
                "package-list",
                item_description=("This item type represents a "
                                "collection of software packages to install."),
                extend_item="software-item",
                packages=Collection("package"),
                name=Property(
                    "basic_string",
                    prop_description="Name of package collection",
                    required=True
                ),
                version=Property(
                    "basic_string",
                    prop_description="Version of package collection",
                )
            ),
            ItemType(
                "package",
                extend_item="software-item",
                item_description=("This item type represents a software "
                                "package to install."),
                name=Property(
                    "basic_string",
                    prop_description="Name of package to install/remove."
                                     "Needs to match the filename of the "
                                     "underlying RPM.",
                    required=True,
                    updatable_plugin=True,
                ),
                version=Property(
                    "package_version",
                    prop_description="Package version to install/remove.",
                ),
                release=Property(
                    "any_string",
                    prop_description="Release number of package to "
                                     "install/remove.",
                ),
                arch=Property(
                    "basic_string",
                    prop_description="Architecture (cpu) of package to "
                                     "install/remove.",
                ),
                config=Property(
                    "package_config",
                    prop_description="Handling of pre-existing configuration "
                                     "files. Must be either 'keep' or "
                                     "'replace'.",
                ),
                repository=Property(
                    "any_string",
                    prop_description="Name of repository to get Package.",
                ),
            )
        ])

    def setup_node(self, **kwargs):
        vpath = kwargs['vpath']
        node = self.create('node', vpath, hostname=kwargs['hostname'])
        self.inherit(
            kwargs['system_vpath'], vpath + '/system')
        self.inherit(
            kwargs['os_profile_vpath'], vpath + '/os')
        self.inherit(
            kwargs['storage_profile_vpath'], vpath + '/storage_profile')
        return node

    # provision a standard ms + 2 node cluster
    def create_system(self):
        self.model.create_root_item('root')
        # inventory
        self.create('os-profile','/software/profiles/rhel_6_4', name='sample-profile',path='/profiles/node-iso',arch='x86_64',breed='redhat')
        # sys0
        self.create('system', '/infrastructure/systems/system0', system_name='MS')
        self.create('disk', '/infrastructure/systems/system0/disks/disk1', name='hd0', size='120G', bootable='true', uuid='ATA_VBOX_HARDDISK_kaboom-1234')
        self.create('nic', '/infrastructure/systems/system0/network_interfaces/nic1', interface_name='eth0', macaddress='08:00:27:F3:7C:C5')
        # sys1
        self.create('system', '/infrastructure/systems/system1', system_name='MN1')
        self.create('disk', '/infrastructure/systems/system1/disks/disk1', name='hd0', size='63G', bootable='true', uuid='ATA_VBOX_HARDDISK_kaboom-1234')
        self.create('nic', '/infrastructure/systems/system1/network_interfaces/nic1', interface_name='eth0', macaddress='08:00:27:5B:C1:3F')
        # sys2
        self.create('system', '/infrastructure/systems/system2', system_name='MN2')
        self.create('disk', '/infrastructure/systems/system2/disks/disk1', name='hd0', size='63G', bootable='true', uuid='ATA_VBOX_HARDDISK_kaboom-1234')
        self.create('nic', '/infrastructure/systems/system2/network_interfaces/nic1', interface_name='eth0', macaddress='08:00:27:65:C8:B4')
        # storage
        self.create('storage-profile','/infrastructure/storage/storage_profiles/profile_1', storage_profile_name='sp1')
        self.create('volume-group', '/infrastructure/storage/storage_profiles/profile_1/volume_groups/vg1', volume_group_name="vg_root")
        self.create('file-system', '/infrastructure/storage/storage_profiles/profile_1/volume_groups/vg1/file_systems/root', type='ext4', mount_point='/',size='20G')
        self.create('file-system', '/infrastructure/storage/storage_profiles/profile_1/volume_groups/vg1/file_systems/swap', type='swap', mount_point='swap',size='2G')
        self.create('physical-device', '/infrastructure/storage/storage_profiles/profile_1/volume_groups/vg1/physical_devices/internal', device_name='hd0')
        # ms
        self.inherit('/infrastructure/systems/system0', '/ms/system')
        self.inherit('/software/profiles/rhel_6_4', '/ms/os')
        # cluster
        self.create('deployment', '/deployments/d1')
        self.create('cluster', '/deployments/d1/clusters/c1')
        self.setup_node(
            vpath='/deployments/d1/clusters/c1/nodes/n1',
            hostname='n1',
            system_vpath='/infrastructure/systems/system1',
            os_profile_vpath='/software/profiles/rhel_6_4',
            storage_profile_vpath='/infrastructure/storage/storage_profiles/profile_1'
        )
        self.setup_node(
            vpath='/deployments/d1/clusters/c1/nodes/n2',
            hostname='n2',
            system_vpath='/infrastructure/systems/system2',
            os_profile_vpath='/software/profiles/rhel_6_4',
            storage_profile_vpath='/infrastructure/storage/storage_profiles/profile_1'
        )
        return self.errors


class QueryItemSanityTests(QueryItemTestCase, TwoNodeMixIn):

    """ sanity test underlying system QueryItem depends on """
    def setUp(self):
        self.setup_common()
        self.register_types()

    def test_create_system(self):
        # check test model is valid
        self.assertEquals([], self.create_system())
        self.assertEquals([], self.model.validate_model())

    def test_get_item(self):
        self.create_system()
        mitem = self.create('package','/software/items/tree', name='tree')
        qitem = QueryItem(self.model, model_item=mitem)
        self.assertEquals(qitem._model_item, mitem)

    def test_query_by_vpath_cmp_create_model_query_item(self):
        self.create_system()
        mitem = self.create('package','/software/items/tree', name='tree')
        qitem_mitem = QueryItem(self.model, mitem)
        qitem_vpath = self.query_by_vpath(mitem.get_vpath())
        self.assertTrue(match_qitem(qitem_mitem, qitem_vpath))

    def test_model_item_reference(self):
        self.create_system()
        mitem = self.create('package','/software/items/tree', name='tree')
        qitem_mitem = QueryItem(self.model, mitem)
        qitem_mitem._updatable = True

        self.model.remove_item('/software/items/tree')

        self.assertEquals([], self.model.query('package', name='tree'))
        self.assertEquals(None, self.model.get_item('/software/items/tree'))
        self.assertEquals(mitem, qitem_mitem._model_item)

        # Only CallbackTasks can change QueryItem attributes and a scenario
        # where the QI's backing ModelItem has been removed from the model by
        # the time the task runs should be made impossible by REST-level model
        # locking.
        # This is just extra insurance
        qitem_mitem.name='newvalue'
        self.assertEquals(None, self.model.get_item('/software/items/tree'))


class TestQueryByVPath(QueryItemTestCase, TwoNodeMixIn):

    def setUp(self):
        self.setup_common()
        self.register_types()
        self.create_system()

    def test_unknown_path(self):
        self.assertRaises(ModelManagerException,self.query_by_vpath,'/a/b/c')

    def test_model_item_found(self):
        mitem = self.create('package','/software/items/tree', name='tree')
        qitem = self.query_by_vpath('/software/items/tree')
        self.assertTrue(qitem._model_item == mitem)

    def test_model_item_not_found(self):
        self.assertRaises(
            ModelManagerException,
            self.query_by_vpath,
            '/software/items/tree')

    def test_get_model_item(self):
        mitem = self.create('package', '/software/items/tree', name='tree')
        qitem = self.query_by_vpath('/software/items/tree')
        self.assertTrue(isinstance(mitem, ModelItem))
        self.assertEquals(qitem.get_vpath(), mitem.get_vpath())
        self.assertEquals(qitem._model_item, mitem)

    def test_get_collection(self):
        vpath = '/deployments/d1/clusters/c1/nodes'
        citem = self.get(vpath)
        qitem = self.query_by_vpath(vpath)
        self.assertTrue(isinstance(citem, CollectionItem))
        self.assertEquals(qitem.get_vpath(), vpath)
        self.assertEquals(qitem._model_item, citem)

    def test_get_ref_collection(self):
        vpath = '/deployments/d1/clusters/c1/nodes/n1/items'
        rcitem = self.get(vpath)
        qitem = self.query_by_vpath(vpath)
        self.assertTrue(isinstance(rcitem, RefCollectionItem))
        self.assertEquals(qitem.get_vpath(), vpath)
        self.assertEquals(qitem._model_item, rcitem)

    def test_query_by_vpath_same_as_query(self):
        mitem = self.create('package', '/software/items/tree', name='tree')
        vpath_qitem = self.query_by_vpath(mitem.get_vpath())
        query_qitem = self.query('package', get_vpath=mitem.get_vpath())[0]
        self.assertTrue(match_qitem(vpath_qitem, query_qitem))

    def test_query_by_vpath_same_as_subquery(self):
        mitem = self.create('package', '/software/items/x', name='x')
        ritem = self.inherit('/software/items/x', '/ms/items/x')
        vpath_qitem = self.query_by_vpath(ritem.get_vpath())
        ms_qitem = self.query('ms')[0]
        subquery_qitem = ms_qitem.query('package')[0]
        self.assertTrue(match_qitem(vpath_qitem, subquery_qitem))

    def test_query_by_vpath_same_as_subquery_by_vpath(self):
        mitem = self.create('package', '/software/items/x', name='x')
        ritem = self.inherit('/software/items/x', '/ms/items/x')
        main_query = self.query_by_vpath(ritem.get_vpath())
        sub_query = main_query.query_by_vpath(ritem.get_vpath())
        self.assertTrue(match_qitem(main_query, sub_query))


class TestQueryMethod(QueryItemTestCase, TwoNodeMixIn):

    def setUp(self):
        self.setup_common()
        self.register_types()
        self.create_system()

    def test_missing_item_type_id(self):
        self.assertRaises(TypeError, self.query)

    def test_item_type_found(self):
        vpath = '/software/items/tree'
        mitem = self.create('package', '/software/items/tree', name='tree')
        result = self.query('package')
        self.assertEquals(result[0]._model_item, mitem)

    def test_item_type_not_found(self):
        result = self.query('package')
        self.assertEqual([], result)

    def test_undefined_type_not_found(self):
        result = self.query('undefined-item-type')
        self.assertEqual([], result)

    def test_query_ms_item(self):
        expected = self.make_query_items(
            self.get('/ms')
        )
        result = self.query('ms')
        self.assertTrue(match_qitems(expected, result))

    def test_query_node_items(self):
        expected = self.make_query_items(
            self.get('/deployments/d1/clusters/c1/nodes/n1'),
            self.get('/deployments/d1/clusters/c1/nodes/n2')
        )
        result = self.query('node')
        self.assertTrue(match_qitems(expected, result))

    def test_cannot_return_items_that_are_inherited_from_another(self):
        expected = self.make_query_items(
            self.create('package','/software/items/x', name='x')
        )
        self.inherit('/software/items/x','/ms/items/x'),
        self.inherit('/software/items/x','/deployments/d1/clusters/c1/software/x')
        self.inherit('/software/items/x','/deployments/d1/clusters/c1/nodes/n1/items/x')
        self.inherit('/software/items/x','/deployments/d1/clusters/c1/nodes/n2/items/x')
        result = self.query('package')
        self.assertTrue(match_qitems(expected, result))

    def test_match_attributes(self):
        expected = self.make_query_items(
            self.create('package','/software/items/a', name='a', release='1.0'),
            self.create('package','/software/items/b', name='b', release='2.0'),
            self.create('package','/software/items/c', name='c', release='2.0'),
            self.create('package','/software/items/d', name='d', release='3.0'),
        )[1:3]
        result = self.query('package', release='2.0')
        self.assertTrue(match_qitems(expected, result))

    def test_match_attributes_fail(self):
        expected = []
        self.create('package','/software/items/a', name='a', release='1.0')
        self.create('package','/software/items/b', name='b', release='2.0')
        self.create('package','/software/items/c', name='c', release='3.0')
        result = self.query('package', release='4.0')
        self.assertTrue(match_qitems(expected, result))

    def test_match_callable(self):
        a = self.create('package','/software/items/a', name='a', release='1.0')
        b = self.create('package','/software/items/b', name='b', release='2.0')
        c = self.create('package','/software/items/c', name='c', release='3.0')
        d = self.create('package','/software/items/d', name='d', release='4.0')
        b.set_updated()
        d.set_updated()
        expected = self.make_query_items(b,d)
        result = self.query('package', is_updated=True)
        self.assertTrue(match_qitems(expected, result))

    def test_match_callable_fail(self):
        items = [
            self.create('package','/software/items/a', name='a', release='1.0'),
            self.create('package','/software/items/b', name='b', release='2.0'),
            self.create('package','/software/items/c', name='c', release='3.0'),
            self.create('package','/software/items/d', name='d', release='4.0')
        ]
        for item in items:
            item.set_updated()
        result = self.query('package', is_updated=False)
        self.assertEquals([], result)

    def test_match_all_properties(self):
        a = self.create('package','/software/items/a', name='a', version='1.0', release='1.0')
        b = self.create('package','/software/items/b', name='b', version='2.0', release='3.0')
        c = self.create('package','/software/items/c', name='c', version='3.0', release='1.0')
        d = self.create('package','/software/items/d', name='d', version='2.0', release='3.0')
        b.set_updated()
        d.set_updated()
        expected = self.make_query_items(b,d)
        result = self.query('package', is_updated=True, version='2.0', release='3.0')
        self.assertTrue(match_qitems(expected, result))

    def test_subquery_by_vpath(self):
        self.create('package','/software/items/tree', name='tree')
        self.inherit('/software/items/tree','/ms/items/tree')
        ms = self.query('ms')[0]
        expected = ms.query('package')
        result = [ ms.query_by_vpath('/ms/items/tree') ]
        self.assertTrue(match_qitems(expected, result))

    def test_subquery_with_python_property_as_criterion(self):
        cluster = self.query('cluster')[0]
        node = cluster.query('node')[0]
        result = cluster.query('node', item_id=node.item_id)
        self.assertEqual(node, result[0])

    def test_subquery_with_callable_as_criterion(self):
        cluster = self.query('cluster')[0]
        all_nodes = cluster.query('node')
        specific_nodes = cluster.query('node', get_state='Initial')
        self.assertEqual(all_nodes, specific_nodes)

    def test_subquery_with_private_callable_as_criterion(self):
        cluster = self.query('cluster')[0]
        node = cluster.query('node')[0]
        crit_value = node._children
        specific_nodes = cluster.query('node', _children=crit_value)
        self.assertFalse(specific_nodes)

    def test_subquery_with_private_property_as_criterion(self):
        cluster = self.query('cluster')[0]
        node = cluster.query('node')[0]
        crit_value = node._updatable
        specific_nodes = cluster.query('node', _updatable=crit_value)
        self.assertFalse(specific_nodes)

    def test_match_multiple_params_regardless_order(self):
        cluster = self.query('cluster')[0]
        nodes = cluster.query('node', is_initial=True, is_node=False)
        self.assertEquals(0, len(nodes))
        nodes = cluster.query('node', is_initial=True, is_node=True)
        self.assertEquals(2, len(nodes))
        nodes = cluster.query('node', is_initial=False, is_node=True)
        self.assertEquals(0, len(nodes))
        nodes = cluster.query('node', is_initial=False, is_node=False)
        self.assertEquals(0, len(nodes))

    def test_query_item_api(self):
        # LITPCDS-12247
        # Check that all public methods for QueryItem api are documented
        # by checking that QueryItem public methods are in ERIClitpdocs
        # and that they have a docstring.

        # Query Item methods published as per
        # ERIClitpdocs/ERIClitpdocs_CXP9030557/rstFiles/plugin_api/index.rst
        # This part of the test will need to be updated if new public methods
        # are added to QueryItem class.
        documented_api =['query', 'clear_property', 'get_ancestor', 'get_cluster', \
                'get_ms', 'is_cluster', 'is_ms', 'is_node', 'query_by_vpath', \
                'is_removed', 'get_state', 'get_source', 'get_vpath', \
                'get_node', 'get_parent', 'parent', 'item_id', 'item_type', \
                'item_type_id', 'vpath', 'is_initial', 'is_applied', \
                'is_updated', 'is_for_removal', 'has_initial_dependencies', \
                'has_updated_dependencies', 'has_removed_dependencies', \
                'properties', 'applied_properties_determinable', \
                'applied_properties']
        query_item_public_methods = [i for i in dir(QueryItem) if not i.startswith('_')]
        # Check that all QueryItem public methods are included in ERIClitpdocs
        set1 = set(documented_api)
        set2 = set(query_item_public_methods)
        self.assertEquals(set(), set1.difference(set2))
        self.assertEquals(set(), set2.difference(set1))

        # Check that all QueryItem public methods have a docstring
        undocumented_methods = set()
        for public_method in query_item_public_methods:
            method = getattr(QueryItem, public_method)
            if getattr(method, '__doc__') is None:
                undocumented_methods.add(public_method)
        self.assertEquals(set(), undocumented_methods)


class TestQueryItemProperties(QueryItemTestCase, TwoNodeMixIn):

    def setUp(self):
        self.setup_common()
        self.register_types()
        self.create_system()

    def test_cascaded_inheritance(self):
        self.create('node', '/deployments/d1/clusters/c1/nodes/n11', hostname='n11')
        self.create('node', '/deployments/d1/clusters/c1/nodes/n12', hostname='n12')
        self.create('node', '/deployments/d1/clusters/c1/nodes/n13', hostname='n13')
        self.inherit("/infrastructure/storage/storage_profiles/profile_1", "/deployments/d1/clusters/c1/nodes/n11/storage_profile")
        self.inherit("/deployments/d1/clusters/c1/nodes/n11/storage_profile", "/deployments/d1/clusters/c1/nodes/n12/storage_profile")
        self.inherit("/deployments/d1/clusters/c1/nodes/n12/storage_profile", "/deployments/d1/clusters/c1/nodes/n13/storage_profile")

        sp = self.query_by_vpath("/infrastructure/storage/storage_profiles/profile_1")
        sp11 = self.query_by_vpath("/deployments/d1/clusters/c1/nodes/n11/storage_profile")
        sp12 = self.query_by_vpath("/deployments/d1/clusters/c1/nodes/n12/storage_profile")
        sp13 = self.query_by_vpath("/deployments/d1/clusters/c1/nodes/n13/storage_profile")
        self.assertEquals(sp.storage_profile_name, sp11.storage_profile_name)
        self.assertEquals(sp.storage_profile_name, sp12.storage_profile_name)
        self.assertEquals(sp.storage_profile_name, sp13.storage_profile_name)

        self.update("/infrastructure/storage/storage_profiles/profile_1", storage_profile_name=sp.storage_profile_name + "_updated")
        sp = self.query_by_vpath("/infrastructure/storage/storage_profiles/profile_1")
        sp11 = self.query_by_vpath("/deployments/d1/clusters/c1/nodes/n11/storage_profile")
        sp12 = self.query_by_vpath("/deployments/d1/clusters/c1/nodes/n12/storage_profile")
        sp13 = self.query_by_vpath("/deployments/d1/clusters/c1/nodes/n13/storage_profile")
        self.assertEquals(sp.storage_profile_name, sp11.storage_profile_name)
        self.assertEquals(sp.storage_profile_name, sp12.storage_profile_name)
        self.assertEquals(sp.storage_profile_name, sp13.storage_profile_name)

    def test_updating_properties_inherited(self):
        self.create('node', '/deployments/d1/clusters/c1/nodes/n3', hostname='n3')
        storage = self.query_by_vpath("/infrastructure/storage/storage_profiles/profile_1")
        original_storage_profile_name = storage.storage_profile_name
        original_root_size = storage.volume_groups.vg1.file_systems.root.size
        self.inherit("/infrastructure/storage/storage_profiles/profile_1", "/deployments/d1/clusters/c1/nodes/n3/storage_profile")

        # check top level
        storage = self.query_by_vpath("/infrastructure/storage/storage_profiles/profile_1")
        node_storage = self.query_by_vpath("/deployments/d1/clusters/c1/nodes/n3/storage_profile")
        self.assertEquals(original_storage_profile_name, storage.storage_profile_name)
        self.assertEquals(original_storage_profile_name, node_storage.storage_profile_name)

        self.update("/infrastructure/storage/storage_profiles/profile_1", storage_profile_name="sp1_updated")
        storage = self.query_by_vpath("/infrastructure/storage/storage_profiles/profile_1")
        node_storage = self.query_by_vpath("/deployments/d1/clusters/c1/nodes/n3/storage_profile")
        self.assertEquals("sp1_updated", storage.storage_profile_name)
        self.assertEquals("sp1_updated", node_storage.storage_profile_name)

        self.update("/deployments/d1/clusters/c1/nodes/n3/storage_profile", storage_profile_name="sp1_updated_n3")
        storage = self.query_by_vpath("/infrastructure/storage/storage_profiles/profile_1")
        node_storage = self.query_by_vpath("/deployments/d1/clusters/c1/nodes/n3/storage_profile")
        self.assertEquals("sp1_updated", storage.storage_profile_name)
        self.assertEquals("sp1_updated_n3", node_storage.storage_profile_name)

        self.update("/infrastructure/storage/storage_profiles/profile_1", storage_profile_name="sp1_updated_again")
        storage = self.query_by_vpath("/infrastructure/storage/storage_profiles/profile_1")
        node_storage = self.query_by_vpath("/deployments/d1/clusters/c1/nodes/n3/storage_profile")
        self.assertEquals("sp1_updated_again", storage.storage_profile_name)
        self.assertEquals("sp1_updated_n3", node_storage.storage_profile_name)

        # check children
        storage = self.query_by_vpath("/infrastructure/storage/storage_profiles/profile_1")
        node_storage = self.query_by_vpath("/deployments/d1/clusters/c1/nodes/n3/storage_profile")
        self.assertEquals(original_root_size, storage.volume_groups.vg1.file_systems.root.size)
        self.assertEquals(original_root_size, node_storage.volume_groups.vg1.file_systems.root.size)

        self.update("/infrastructure/storage/storage_profiles/profile_1/volume_groups/vg1/file_systems/root", size="42G")
        storage = self.query_by_vpath("/infrastructure/storage/storage_profiles/profile_1")
        node_storage = self.query_by_vpath("/deployments/d1/clusters/c1/nodes/n3/storage_profile")
        self.assertEquals("42G", storage.volume_groups.vg1.file_systems.root.size)
        self.assertEquals("42G", node_storage.volume_groups.vg1.file_systems.root.size)

        self.update("/deployments/d1/clusters/c1/nodes/n3/storage_profile/volume_groups/vg1/file_systems/root", size="43G")
        storage = self.query_by_vpath("/infrastructure/storage/storage_profiles/profile_1")
        node_storage = self.query_by_vpath("/deployments/d1/clusters/c1/nodes/n3/storage_profile")
        self.assertEquals("42G", storage.volume_groups.vg1.file_systems.root.size)
        self.assertEquals("43G", node_storage.volume_groups.vg1.file_systems.root.size)

        self.update("/infrastructure/storage/storage_profiles/profile_1/volume_groups/vg1/file_systems/root", size="44G")
        storage = self.query_by_vpath("/infrastructure/storage/storage_profiles/profile_1")
        node_storage = self.query_by_vpath("/deployments/d1/clusters/c1/nodes/n3/storage_profile")
        self.assertEquals("44G", storage.volume_groups.vg1.file_systems.root.size)
        self.assertEquals("43G", node_storage.volume_groups.vg1.file_systems.root.size)


class TestQueryItemStatesForModelItem(QueryItemTestCase, TwoNodeMixIn):

    def setUp(self):
        self.setup_common()
        self.register_types()
        self.create_system()
        self.mitem = self.create('package','/software/items/tree', name='tree')

    # initial state tests
    def test_is_initial_true(self):
        self.mitem.set_initial()
        qitem = self.query('package')[0]
        self.assertTrue(qitem.is_initial())

    def test_is_initial_false_when_applied(self):
        self.mitem.set_applied()
        qitem = self.query('package')[0]
        self.assertFalse(qitem.is_initial())

    def test_is_initial_false_when_updated(self):
        self.mitem.set_updated()
        qitem = self.query('package')[0]
        self.assertFalse(qitem.is_initial())

    def test_is_initial_false_when_for_removal(self):
        self.mitem.set_for_removal()
        qitem = self.query('package')[0]
        self.assertFalse(qitem.is_initial())

    def test_is_initial_false_when_removed(self):
        self.mitem.set_removed()
        qitem = self.query('package')[0]
        self.assertFalse(qitem.is_initial())

    # applied state tests
    def test_is_applied_true(self):
        self.mitem.set_applied()
        qitem = self.query('package')[0]
        self.assertTrue(qitem.is_applied())

    def test_is_applied_false_when_initial(self):
        self.mitem.set_initial()
        qitem = self.query('package')[0]
        self.assertFalse(qitem.is_applied())

    def test_is_applied_false_when_updated(self):
        self.mitem.set_updated()
        qitem = self.query('package')[0]
        self.assertFalse(qitem.is_applied())

    def test_is_applied_false_when_for_removal(self):
        self.mitem.set_for_removal()
        qitem = self.query('package')[0]
        self.assertFalse(qitem.is_applied())

    def test_is_applied_false_when_removed(self):
        self.mitem.set_removed()
        qitem = self.query('package')[0]
        self.assertFalse(qitem.is_applied())

    # updated tests
    def test_is_updated_true(self):
        self.mitem.set_updated()
        qitem = self.query('package')[0]
        self.assertTrue(qitem.is_updated())

    def test_is_updated_false_when_initial(self):
        self.mitem.set_initial()
        qitem = self.query('package')[0]
        self.assertFalse(qitem.is_updated())

    def test_is_updated_false_when_applied(self):
        self.mitem.set_applied()
        qitem = self.query('package')[0]
        self.assertFalse(qitem.is_updated())

    def test_is_updated_false_when_for_removal(self):
        self.mitem.set_for_removal()
        qitem = self.query('package')[0]
        self.assertFalse(qitem.is_updated())

    def test_is_updated_false_when_removed(self):
        self.mitem.set_removed()
        qitem = self.query('package')[0]
        self.assertFalse(qitem.is_updated())

    # for removal
    def test_is_for_removal_true(self):
        self.mitem.set_for_removal()
        qitem = self.query('package')[0]
        self.assertTrue(qitem.is_for_removal())

    def test_is_for_removal_false_when_initial(self):
        self.mitem.set_initial()
        qitem = self.query('package')[0]
        self.assertFalse(qitem.is_for_removal())

    def test_is_for_removal_false_when_applied(self):
        self.mitem.set_applied()
        qitem = self.query('package')[0]
        self.assertFalse(qitem.is_for_removal())

    def test_is_for_removal_false_when_updated(self):
        self.mitem.set_updated()
        qitem = self.query('package')[0]
        self.assertFalse(qitem.is_for_removal())

    def test_is_for_removal_false_when_removed(self):
        self.mitem.set_removed()
        qitem = self.query('package')[0]
        self.assertFalse(qitem.is_for_removal())

    # Removed tests
    def test_is_removed_true(self):
        self.mitem.set_removed()
        qitem = self.query('package')[0]
        self.assertTrue(qitem.is_removed())

    def test_is_removed_false_when_initial(self):
        self.mitem.set_initial()
        qitem = self.query('package')[0]
        self.assertFalse(qitem.is_removed())

    def test_is_removed_false_when_applied(self):
        self.mitem.set_applied()
        qitem = self.query('package')[0]
        self.assertFalse(qitem.is_removed())

    def test_is_removed_false_when_updated(self):
        self.mitem.set_updated()
        qitem = self.query('package')[0]
        self.assertFalse(qitem.is_removed())

    def test_is_removed_false_when_for_removal(self):
        self.mitem.set_for_removal()
        qitem = self.query('package')[0]
        self.assertFalse(qitem.is_removed())

    def test_set_removed_sets_model(self):
        qitem = self.query('package')[0]
        self.assertRaises(AttributeError, getattr, qitem, 'set_removed')
        self.assertTrue(qitem._model_item.is_initial())
        qitem._model_item.set_removed()
        self.assertTrue(qitem.is_removed())

    def test_set_applied_sets_model(self):
        qitem = self.query('package')[0]
        self.assertRaises(AttributeError, getattr, qitem, 'set_applied')
        self.assertTrue(qitem._model_item.is_initial())
        qitem._model_item.set_applied()
        self.assertTrue(qitem.is_applied())


class QueryItemIntrospectionTest(unittest.TestCase):
    def setUp(self):
        self.model = ModelManager()
        self.model.register_property_type(
            PropertyType("any_string", regex=r"^.*$"))
        self.model.register_item_types([
            ItemType("required-child"),
            ItemType("optional-child"),
            ItemType("required-coll-item"),
            ItemType("optional-coll-item"),
            ItemType("required-ref-source"),
            ItemType("optional-ref-source"),
            ItemType(
                "test-item",
                item_description="test item type.",
                required_property=Property("any_string", required=True,),
                optional_property=Property("any_string", required=False,),
                required_child=Child("required-child", required=True),
                optional_child=Child("optional-child", required=False),
                required_reference=Reference("required-ref-source",
                                             required=True),
                optional_reference=Reference("optional-ref-source",
                                             required=False),
                required_collection=Collection("required-coll-item",
                                               min_count=1),
                optional_collection=Collection("optional-coll-item"),
                required_ref_collection=RefCollection("required-ref-source",
                                                      min_count=1),
                optional_ref_collection=RefCollection("optional-ref-source"),
            ),
            ItemType("root",
                     test_item=Child("test-item"),
                     required_ref_source=Child("required-ref-source")
                     )

        ])

        self.model.create_root_item("root")
        self.model.create_item("required-ref-source", '/required_ref_source')
        self.model.create_item("test-item", "/test_item",
                               required_property="foobar")
        self.model.create_item("required-child", "/test_item/required_child")
        self.model.create_item("required-coll-item",
                               "/test_item/required_collection/item1")
        self.model.create_inherited('/required_ref_source',
                                    '/test_item/required_reference')
        self.model.create_inherited('/required_ref_source',
                                    '/test_item/required_ref_collection/item1')

        self.model.query('test-item')
        self.test_item = QueryItem(self.model,
                self.model.query_by_vpath('/test_item'))

    def test_has_regular_attrs(self):
        result = dir(self.test_item)
        self.assertTrue(set(vars(QueryItem).keys()).issubset(result))

    def test_has_attr_names_for_required_properties(self):
        result = dir(self.test_item)
        present = ['required_property', 'required_child', 'required_reference',
                   'required_collection', 'required_ref_collection']
        self.assertTrue(set(present).issubset(result))

    def test_has_no_attr_names_for_optional_unset_properties(self):
        result = dir(self.test_item)
        absent = ['optional_property', 'optional_child', 'optional_reference',
                  'optional_collection', 'optional_ref_collection', ]
        self.assertFalse(set(absent).issubset(result))

    def test_output_has_no_duplicate_values(self):
        result = dir(self.test_item)
        self.assertEquals(len(result), len(set(result)))

    def test_output_sorted_alphabetically(self):
        result = dir(self.test_item)
        self.assertEquals(result, sorted(result))
