import unittest
from mock import patch, call
from mock import MagicMock
import os
import sys
import platform
from litp.core.iso_import import IsoParser, IsoImporter, run_detached_child
from litp.core.exceptions import InvalidIsoException, ForkError, RpcExecutionException
from litp.core.rpc_commands import PuppetExecutionProcessor, PuppetCatalogRunProcessor
from litp.core.yum_upgrade import YumImport
from litp.core.maintenance import StateFile
from litp.metrics import set_handlers

class FsNode(object):
    def __init__(self, name, parent, size=1024):
        self.parent = parent
        self.name = name
        self.size = size

    @property
    def path(self):
        if self.parent:
            return os.path.join(self.parent.path, self.name)
        else:
            return '/'

    def stat(self):
        class dummy_statinfo(object):
            def __init__(self):
                self.st_size = 0

        statinfo = dummy_statinfo()
        statinfo.st_size = self.size
        return statinfo

    def isfile(self):
        return False

    def isdir(self):
        return False

    def listdir(self):
        raise OSError(20, "Not a directory: '%s'" % self.path)

    def get_child(self, name):
        raise OSError(2,
            "No such file or directory: '%s'" % \
            os.path.join(self.path, name))

class Dir(FsNode):
    def __init__(self, name, parent):
        super(Dir, self).__init__(name, parent)
        self.children = {}

    def isdir(self):
        return True

    def add_child(self, node):
        self.children[node.name] = node

    def get_child(self, name):
        if name in self.children:
            return self.children[name]
        return super(Dir, self).get_child(name)

    def listdir(self):
        return [n for n in self.children.keys()]

class File(FsNode):
    def __init__(self, name, parent, size):
        super(File, self).__init__(name, parent, size=size)

    def isfile(self):
        return True

class DirSpec(object):
    def __init__(self, name, children=None):
        self.name = name
        if children == None:
            self.children = []
        else:
            self.children = children

    def get_node(self, parent):
        node = Dir(self.name, parent)
        for child in self.children:
            node.add_child(child.get_node(node))
        return node

class FileSpec(object):
    def __init__(self, name, size=1024):
        self.name = name
        self.size = size

    def get_node(self, parent):
        return File(self.name, parent, self.size)

class MountPoint(object):
    def __init__(self, parent_path, dirspec):
        self.parent_path = parent_path
        self.dirspec = dirspec

class MockFS(object):
    def __init__(self):
        self.root = Dir(None, None)

    def mount_directory(self, path, children=None):
        head, tail = os.path.split(path)
        parent = self.makedirs(head)
        d = DirSpec(tail, children).get_node(parent)
        parent.add_child(d)
        return d

    def _get_node(self, path):
        if path == '/':
            return self.root
        sys.stdout.flush()
        head, tail = os.path.split(path)
        parent = self._get_node(head)
        return parent.get_child(tail)

    def makedirs(self, path):
        try:
            return self._get_node(path)
        except Exception as e:
            head, tail = os.path.split(path)
            parent = self.makedirs(head)
            d = Dir(tail, parent)
            parent.add_child(d)
            return d

    def mock_path_exists(self, path):
        try:
            node = self._get_node(path)
            return True
        except Exception as e:
            return False

    def mock_path_isdir(self, path):
        try:
            node = self._get_node(path)
            return node.isdir()
        except Exception as e:
            return False

    def mock_path_isfile(self, path):
        try:
            node = self._get_node(path)
            return node.isfile()
        except Exception as e:
            return False

    def mock_stat(self, path):
        try:
            node = self._get_node(path)
            return node.stat()
        except Exception as e:
            #return False
            raise

    def mock_listdir(self, path):
        return self._get_node(path).listdir()

class MockFsTestCase(unittest.TestCase):

    def _add_patch(self, name, callable):
        p = patch(name, callable)
        p.start()
        self._patches.append(p)

    def setUp(self):
        self.os_ver = platform.linux_distribution()[2][0]
        self.mockfs = MockFS()
        self._patches = []
        self._add_patch('litp.core.iso_import.os.path.exists', self.mockfs.mock_path_exists)
        self._add_patch('litp.core.iso_import.os.path.isdir', self.mockfs.mock_path_isdir)
        self._add_patch('litp.core.iso_import.os.path.isfile', self.mockfs.mock_path_isfile)
        self._add_patch('litp.core.iso_import.stat', self.mockfs.mock_stat)
        self._add_patch('litp.core.iso_import.os.listdir', self.mockfs.mock_listdir)
        self._add_patch('litp.core.iso_import.platform.linux_distribution', self.mock_dist)
        self.PuppetExecutionProcessor_cached = PuppetExecutionProcessor.trigger_and_wait
        self.YumImporter_cached = YumImport.import_packages
        PuppetExecutionProcessor.trigger_and_wait = MagicMock()
        YumImport.import_packages = MagicMock()
        YumImport.import_packages.return_value = 0

    def tearDown(self):
        PuppetExecutionProcessor.trigger_and_wait = self.PuppetExecutionProcessor_cached
        YumImport.import_packages = self.YumImporter_cached
        for p in self._patches:
            p.stop()

    def mock_dist(self):
        return None, self.os_ver, None

class IsoParserTest(MockFsTestCase):

    def _assert_invalid(self, parser):
        self.assertRaises(InvalidIsoException, parser.get_actions)

    def test_source_does_not_exist(self):
        self.mockfs.mount_directory('/tmp')
        parser = IsoParser('/tmp/test_iso')
        self.assertEquals(
            parser.validate(),
            [
                'Source directory "/tmp/test_iso" does not exist.',
            ]
        )
        self._assert_invalid(parser)

    def test_source_exists_but_is_not_a_directory(self):
        self.mockfs.mount_directory('/tmp', [FileSpec('test_iso')])
        parser = IsoParser('/tmp/test_iso')
        self.assertEquals(
            parser.validate(),
            [
                'Source path "/tmp/test_iso" exists but is not a directory.',
            ]
        )
        self._assert_invalid(parser)

    def test_source_is_not_an_absolute_path(self):
        self.mockfs.mount_directory('/tmp', [FileSpec('test_iso')])
        parser = IsoParser('tmp/test_iso')
        self.assertEquals(
            parser.validate(),
            [
                'Source path "tmp/test_iso" must be an absolute path.',
            ]
        )
        self._assert_invalid(parser)

    def test_source_exists_ok(self):
        self.mockfs.mount_directory('/tmp/test_iso')
        parser = IsoParser('/tmp/test_iso')
        self.assertEquals(
            parser.validate(),
            [
                'No LITP compliant ISO to import',
            ]
        )
        self._assert_invalid(parser)

    def test_litp_plugins_empty(self):
        self.mockfs.mount_directory('/tmp/test_iso/litp/plugins')
        parser = IsoParser('/tmp/test_iso')
        self.assertEquals(parser.validate(), [])
        self.assertEquals(parser.get_actions(),
            [
                {
                    'verb': 'DISABLE_PUPPET',
                    'args': {}
                },
                {
                    'verb': 'RSYNC_RPMS',
                    'args': {
                        'source': '/tmp/test_iso/litp/plugins',
                        'destination': '/var/www/html/litp'
                    }
                },
                {
                    'verb': 'CREATE_REPO',
                    'args': {
                        'directory': '/var/www/html/litp'
                    }
                },
                {
                    'verb': 'CLEAN_YUM_CACHE',
                    'args': {}
                },
                {
                    'verb': 'INSTALL_RPMS',
                    'args': {}
                },
                {
                    'verb': 'ENABLE_PUPPET',
                    'args': {}
                }
            ]
        )

    def test_litp_plugins_with_rpms(self):
        self.mockfs.mount_directory('/tmp/test_iso/litp/plugins',
            [
                FileSpec('ERIClitpfoobar_CXP1234567-2.3.4.noarch.rpm'),
            ]
        )
        parser = IsoParser('/tmp/test_iso')
        self.assertEquals(parser.validate(), [])
        self.assertEquals(parser.get_actions(),
            [
                {
                    'verb': 'DISABLE_PUPPET',
                    'args': {}
                },
                {
                    'verb': 'RSYNC_RPMS',
                    'args': {
                        'source': '/tmp/test_iso/litp/plugins',
                        'destination': '/var/www/html/litp'
                    }
                },
                {
                    'verb': 'CREATE_REPO',
                    'args': {
                        'directory': '/var/www/html/litp'
                    }
                },
                {
                    'verb': 'CLEAN_YUM_CACHE',
                    'args': {}
                },
                {
                    'verb': 'INSTALL_RPMS',
                    'args': {}
                },
                {
                    'verb': 'ENABLE_PUPPET',
                    'args': {}
                }
            ]
        )

    def test_litp_plugins_with_empty_rpm(self):
        self.mockfs.mount_directory('/tmp/test_iso/litp/plugins',
            [
                FileSpec('somefile.rpm', size=0),
            ]
        )
        parser = IsoParser('/tmp/test_iso')
        self.assertEquals(parser.validate(),
            [
                'File "/tmp/test_iso/litp/plugins/somefile.rpm" '
                        'is of zero length.',
            ]
        )
        self._assert_invalid(parser)


    def test_litp_plugins_with_empty_xml_file(self):
        self.mockfs.mount_directory('/tmp/test_iso/litp/plugins',
            [
                FileSpec('comps.xml', size=0),
            ]
        )
        parser = IsoParser('/tmp/test_iso')
        self.assertEquals(parser.validate(),
            [
                'File "/tmp/test_iso/litp/plugins/comps.xml" '
                        'is of zero length.',
            ]
        )
        self._assert_invalid(parser)


    def test_litp_plugins_with_rpms_and_xml(self):
        self.mockfs.mount_directory('/tmp/test_iso/litp/plugins',
            [
                FileSpec('ERIClitpfoobar_CXP1234567-2.3.4.noarch.rpm'),
                FileSpec('comps.xml'),
            ]
        )
        parser = IsoParser('/tmp/test_iso')
        self.assertEquals(parser.validate(), [])
        self.assertEquals(parser.get_actions(),
            [
                {
                    'verb': 'DISABLE_PUPPET',
                    'args': {}
                },
                {
                    'verb': 'RSYNC_RPMS',
                    'args': {
                        'source': '/tmp/test_iso/litp/plugins',
                        'destination': '/var/www/html/litp'
                    }
                },
                {
                    'verb': 'CREATE_REPO',
                    'args': {
                        'directory': '/var/www/html/litp'
                    }
                },
                {
                    'verb': 'CLEAN_YUM_CACHE',
                    'args': {}
                },
                {
                    'verb': 'INSTALL_RPMS',
                    'args': {}
                },
                {
                    'verb': 'ENABLE_PUPPET',
                    'args': {}
                }
            ]
        )


    def test_litp_plugins_is_file(self):
        self.mockfs.mount_directory('/tmp/test_iso/litp',
            [
                FileSpec('plugins'),
            ]
        )
        parser = IsoParser('/tmp/test_iso')
        self.assertEquals(parser.validate(),
            [
                'Source path "/tmp/test_iso/litp/plugins" '
                    'exists but is not a directory',
            ]
        )
        self._assert_invalid(parser)


    def test_product_plugins_ok(self):
        self.mockfs.mount_directory('/tmp/test_iso/litp/plugins/BOB',
            [
                FileSpec('ERIClitpbobplugin-1.2.3.noarch.rpm'),
            ]
        )
        parser = IsoParser('/tmp/test_iso')
        self.assertEquals(parser.validate(), [])
        self.assertEquals(parser.get_actions(),
            [
                {
                    'verb': 'DISABLE_PUPPET',
                    'args': {}
                },
                {
                    'verb': 'RSYNC_RPMS',
                    'args': {
                        'source': '/tmp/test_iso/litp/plugins',
                        'destination': '/var/www/html/litp'
                    }
                },
                {
                    'verb': 'CREATE_REPO',
                    'args': {
                        'directory': '/var/www/html/litp'
                    }
                },
                {
                    'verb': 'RSYNC_RPMS',
                    'args': {
                        'source': '/tmp/test_iso/litp/plugins/BOB',
                        'destination': '/var/www/html/litp_plugins'
                    }
                },
                {
                    'verb': 'CREATE_REPO',
                    'args': {
                        'directory': '/var/www/html/litp_plugins'
                    }
                },
                {
                    'verb': 'CLEAN_YUM_CACHE',
                    'args': {}
                },
                {
                    'verb': 'INSTALL_RPMS',
                    'args': {}
                },
                {
                    'verb': 'ENABLE_PUPPET',
                    'args': {}
                }
            ]
        )

    def test_repos_dir_empty(self):
        self.mockfs.mount_directory('/tmp/test_iso/repos')
        parser = IsoParser('/tmp/test_iso')
        self.assertEquals(parser.validate(),
            [
                'No LITP compliant ISO to import',
            ]
        )
        self._assert_invalid(parser)

    def test_repos_not_a_directory(self):
        self.mockfs.mount_directory('/tmp/test_iso', [FileSpec('repos')])
        parser = IsoParser('/tmp/test_iso')
        self.assertEquals(parser.validate(),
            [
                'Source path "/tmp/test_iso/repos" '
                    'exists but is not a directory.',
            ]
        )
        self._assert_invalid(parser)

    def test_repos_ok_dest_non_existent(self):
        self.mockfs.mount_directory('/tmp/test_iso/repos/FOO',
            [
                FileSpec('foo_core-1.0.1.noarch.rpm'),
            ]
        )
        parser = IsoParser('/tmp/test_iso')
        self.assertEquals(parser.validate(), [])
        self.assertEquals(parser.get_actions(),
            [
                {
                    'verb': 'DISABLE_PUPPET',
                    'args': {}
                },
                {
                    'verb': 'RSYNC_RPMS',
                    'args': {
                        'source': '/tmp/test_iso/repos/FOO',
                        'destination': '/var/www/html/FOO_rhel' + self.os_ver
                    }
                },
                {
                    'verb': 'CREATE_REPO',
                    'args': {
                        'directory': '/var/www/html/FOO_rhel' + self.os_ver
                    }
                },
                {
                    'verb': 'CLEAN_YUM_CACHE',
                    'args': {}
                },
                {
                    'verb': 'INSTALL_RPMS',
                    'args': {}
                },
                {
                    'verb': 'ENABLE_PUPPET',
                    'args': {}
                }
            ]
        )

    def test_repos_ok_dest_is_directory(self):
        self.mockfs.mount_directory('/var/www/html/FOO' + self.os_ver)
        return self.test_repos_ok_dest_non_existent()

    def test_repos_dest_is_not_directory(self):
        self.mockfs.mount_directory('/var/www/html',
            [
                FileSpec('FOO_rhel' + self.os_ver),
            ]
        )
        self.mockfs.mount_directory('/tmp/test_iso/repos/FOO',
            [
                FileSpec('foo_core-1.0.1.noarch.rpm'),
            ]
        )
        parser = IsoParser('/tmp/test_iso')
        self.assertEquals(parser.validate(),
            [
                'Destination path "/var/www/html/FOO_rhel{0}" '
                    'exists but is not a directory'.format(self.os_ver),
            ]
        )
        self._assert_invalid(parser)

    def test_repo_subproject_ok_dest_non_existent(self):
        self.mockfs.mount_directory(
            '/tmp/test_iso/repos/FOO/gizmos',
            [
                FileSpec('foo_green_gizmo-1.0.1.rpm'),
            ]
        )
        parser = IsoParser('/tmp/test_iso')
        self.assertEquals(parser.validate(), [])
        self.assertEquals(parser.get_actions(),
            [
                {
                    'verb': 'DISABLE_PUPPET',
                    'args': {}
                },
                {
                    'verb': 'RSYNC_RPMS',
                    'args': {
                        'source': '/tmp/test_iso/repos/FOO',
                        'destination': '/var/www/html/FOO_rhel' + self.os_ver
                    }
                },
                {
                    'verb': 'CREATE_REPO',
                    'args': {
                        'directory': '/var/www/html/FOO_rhel' + self.os_ver
                    }
                },
                {
                    'verb': 'RSYNC_RPMS',
                    'args': {
                        'source': '/tmp/test_iso/repos/FOO/gizmos',
                        'destination': '/var/www/html/FOO_gizmos_rhel' +\
                                        self.os_ver
                    }
                },
                {
                    'verb': 'CREATE_REPO',
                    'args': {
                        'directory': '/var/www/html/FOO_gizmos_rhel' +\
                                     self.os_ver
                    }
                },
                {
                    'verb': 'CLEAN_YUM_CACHE',
                    'args': {}
                },
                {
                    'verb': 'INSTALL_RPMS',
                    'args': {}
                },
                {
                    'verb': 'ENABLE_PUPPET',
                    'args': {}
                }
            ]
        )

    def test_images_empty(self):
        self.mockfs.mount_directory('/tmp/test_iso/images')
        parser = IsoParser('/tmp/test_iso')
        self.assertEquals(parser.validate(), [])
        self.assertEquals(parser.get_actions(),
            [
                {
                    'verb': 'RSYNC_IMAGES',
                    'args': {
                        'source': '/tmp/test_iso',
                    }
                },
                {
                    'verb': 'DISABLE_PUPPET',
                    'args': {}
                },
                {
                    'verb': 'INSTALL_RPMS',
                    'args': {}
                },
                {
                    'verb': 'ENABLE_PUPPET',
                    'args': {}
                }
            ]
        )

    def test_images_not_a_directory(self):
        self.mockfs.mount_directory('/tmp/test_iso', [FileSpec('images')])
        parser = IsoParser('/tmp/test_iso')
        self.assertEquals(parser.validate(),
            [
                'Source path "/tmp/test_iso/images" '
                    'exists but is not a directory.',
            ]
        )
        self._assert_invalid(parser)

    def test_images_with_file_under_images_root_invalid(self):
        self.mockfs.mount_directory('/tmp/test_iso/images',
            [
                FileSpec('rhel-server-6.6-x86_64-dvd.iso'),
            ]
        )
        parser = IsoParser('/tmp/test_iso')
        self.assertEquals(
            parser.validate(),
            [
                'Source path "/tmp/test_iso/images/rhel-server-6.6-x86_64-dvd.iso" '
                'exists but is not a directory.',
            ]
        )

    def test_images_with_project_folders(self):
        self.mockfs.mount_directory(
            '/tmp/test_iso/images/RHEL6',
            [
                FileSpec('rhel-server-6.6-x86_64-dvd.iso'),
            ]
        )
        parser = IsoParser('/tmp/test_iso')
        self.assertEquals(parser.validate(), [])
        self.assertEquals(parser.get_actions(),
            [
                {
                    'verb': 'RSYNC_IMAGES',
                    'args': {
                        'source': '/tmp/test_iso',
                    }
                },
                {
                    'verb': 'GENERATE_CHECKSUM',
                    'args': {
                        'image_filepath': '/tmp/test_iso/images/RHEL6/rhel-server-6.6-x86_64-dvd.iso',
                        'destination': '/var/www/html/images/RHEL6'
                    }
                },
                {
                    'verb': 'VERIFY_CHECKSUM',
                    'args': {
                        'image_filename': 'rhel-server-6.6-x86_64-dvd.iso',
                        'directory': '/var/www/html/images/RHEL6'
                    }
                },
                {
                    'verb': 'DISABLE_PUPPET',
                    'args': {}
                },
                {
                    'verb': 'INSTALL_RPMS',
                    'args': {}
                },
                {
                    'verb': 'ENABLE_PUPPET',
                    'args': {}
                }
            ]
        )

    def test_empty_image(self):
        self.mockfs.mount_directory(
            '/tmp/test_iso/images/RHEL6',
            [
                FileSpec('something.qcow2', size=0),
            ]
        )
        parser = IsoParser('/tmp/test_iso')
        self.assertEquals(parser.validate(),
            [
                'File "/tmp/test_iso/images/RHEL6/something.qcow2" '
                        'is of zero length.',
            ]
        )

    def test_images_with_subproject_folders(self):
        self.mockfs.mount_directory(
            '/tmp/test_iso/images/RHEL6/6.6',
            [
                FileSpec('rhel-server-6.6-x86_64-dvd.iso'),
            ]
        )
        parser = IsoParser('/tmp/test_iso')
        self.assertEquals(parser.validate(), [])
        self.assertEquals(parser.get_actions(),
            [
                {
                    'verb': 'RSYNC_IMAGES',
                    'args': {
                        'source': '/tmp/test_iso',
                    }
                },
                {
                    'verb': 'GENERATE_CHECKSUM',
                    'args': {
                        'image_filepath': '/tmp/test_iso/images/RHEL6/6.6/rhel-server-6.6-x86_64-dvd.iso',
                        'destination': '/var/www/html/images/RHEL6/6.6'
                    }
                },
                {
                    'verb': 'VERIFY_CHECKSUM',
                    'args': {
                        'image_filename': 'rhel-server-6.6-x86_64-dvd.iso',
                        'directory': '/var/www/html/images/RHEL6/6.6'
                    }
                },
                {
                    'verb': 'DISABLE_PUPPET',
                    'args': {}
                },
                {
                    'verb': 'INSTALL_RPMS',
                    'args': {}
                },
                {
                    'verb': 'ENABLE_PUPPET',
                    'args': {}
                }
            ]
        )

    def test_images_with_md5_subproject_folders(self):
        self.mockfs.mount_directory(
            '/tmp/test_iso/images/RHEL6/6.6',
            [
                FileSpec('rhel-server-6.6-x86_64-dvd.iso'),
                FileSpec('rhel-server-6.6-x86_64-dvd.iso.md5'),
            ]
        )
        parser = IsoParser('/tmp/test_iso')
        self.assertEquals(parser.validate(), [])
        self.assertEquals(parser.get_actions(),
            [
                {
                    'verb': 'VERIFY_CHECKSUM',
                    'args': {
                        'image_filename': 'rhel-server-6.6-x86_64-dvd.iso',
                        'directory': '/tmp/test_iso/images/RHEL6/6.6'
                    }
                },
                {
                    'verb': 'RSYNC_IMAGES',
                    'args': {
                        'source': '/tmp/test_iso',
                    }
                },
                {
                    'verb': 'VERIFY_CHECKSUM',
                    'args': {
                        'image_filename': 'rhel-server-6.6-x86_64-dvd.iso',
                        'directory': '/var/www/html/images/RHEL6/6.6'
                    }
                },
                {
                    'verb': 'DISABLE_PUPPET',
                    'args': {}
                },
                {   'verb': 'INSTALL_RPMS',
                    'args': {}
                },
                {
                    'verb': 'ENABLE_PUPPET',
                    'args': {}
                }
            ]
        )

    def test_repos_ok_dest_is_directory(self):
        self.mockfs.mount_directory('/var/www/html/RHEL6')
        return self.test_images_with_project_folders()

    def test_repos_ok_dest_is_subdirectory(self):
        self.mockfs.mount_directory('/var/www/html/RHEL6/6.6')
        return self.test_images_with_subproject_folders()

class IsoImporterTest(MockFsTestCase):

    def setUp(self):
        super(IsoImporterTest, self).setUp()
        self._errors = []
        self._add_patch('litp.core.iso_import.log.trace.error', self.mock_log_error)
        self._add_patch('litp.core.iso_import.run_rpc_command', self.mock_run_rpc_command)
        self._add_patch('litp.core.rpc_commands.PuppetMcoProcessor.run_puppet', self.mock_run_puppet)
        self._add_patch('litp.core.rpc_commands.PuppetExecutionProcessor.wait', MagicMock())
        self._add_patch('litp.core.rpc_commands.PuppetCatalogRunProcessor.trigger_and_wait', MagicMock())
        self._add_patch('litp.core.rpc_commands.PuppetCatalogRunProcessor.update_config_version', MagicMock(return_value='test'))
        self._fake_statefile = patch('litp.core.iso_import.StateFile')
        self._statefile = self._fake_statefile.start()

    def tearDown(self):
        self._fake_statefile.stop()
        #self._fake_write_state.stop()
        super(IsoImporterTest, self).tearDown()

    def mock_log_error(self, msg, exc_info=''):
        self._errors.append(msg)

    def _rpc_result(self, nodes, errors, status, err):
        results = {}
        for node in nodes:
            results[node] = {
                'errors': errors,
                'data': {
                    'status': status,
                    'err': err,
                    'out': '',
                }
            }
        return results

    def _good_rpc_result(self, nodes):
        return self._rpc_result(nodes, '', 0, '')

    def _bad_rpc_result(self, nodes):
        return self._rpc_result(nodes, ['Bad input'], 1, 'Test failed')

    def _set_expected_call_data(self, call_data):
        self._expected_call_data = call_data
        self._calls = []
        self._call_index = 0

    def mock_run_rpc_command(self, nodes, agent, action,
                    action_kwargs=None, deadline=None, retries=0):
        return self._mock_rpc_run('run_rpc_command', nodes, agent, action,
                    action_kwargs=action_kwargs, deadline=deadline, retries=retries)

    def mock_run_puppet(self, nodes, agent, action,
                    action_kwargs=None, deadline=None):
        return self._mock_rpc_run('run_puppet', nodes, agent, action,
                    action_kwargs=action_kwargs, deadline=deadline)

    def _mock_rpc_run(self, method_name, nodes, agent, action,
                    action_kwargs=None, deadline=None, retries=0):

        inputs = {
            'nodes': nodes,
            'agent': agent,
            'action': action,
            'action_kwargs': action_kwargs
        }

        print 'inputs: %s' % inputs
        expected = self._expected_call_data[self._call_index]
        self._call_index += 1

        self.assertEquals(method_name, expected['method'])
        self.assertEquals(inputs, expected['in'])

        if inputs == expected['in']:
            results = expected['out']
        else:
            results = self._bad_rpc_result(nodes)

        self._calls.append({
            'method': method_name,
            'in': inputs,
            'out': results
        })

        print 'results: %s' % results
        return results

    def _assert_import_success(self):
        self.assertEquals(self.importer.run(), self.importer.RC_SUCCESS)
        self.assertEquals(self._calls, self._expected_call_data)
        self.assertEquals(
            self._statefile.method_calls,
            [
                call.write_state(self._statefile.STATE_RUNNING),
                call.write_state(self._statefile.STATE_DONE),
            ]
        )

    def _assert_import_failure(self, errors):
        self.assertEquals(self.importer.run(), self.importer.RC_ERROR)
        self.assertEquals(self._errors[-1], 'ISO Importer failure: %s' % errors)
        self.assertEquals(
            self._statefile.method_calls,
            [
                call.write_state(self._statefile.STATE_RUNNING),
                call.write_state(self._statefile.STATE_FAILED),
            ]
        )

    @patch('litp.metrics.set_handlers')
    def test_source_does_not_exist(self, mock_set_handlers):
        self.mockfs.mount_directory('/tmp')
        self.importer = IsoImporter('/tmp/test_iso', 'ms1', ['node1', 'node2'])
        self.importer._write_file = MagicMock()
        self.importer._exists = MagicMock(return_value=False)
        self.importer._open_file = MagicMock()
        self.importer._fchmod = MagicMock()
        self.importer._touch_sitepp_file = MagicMock()
        self._assert_import_failure(
            [
                'Source directory "/tmp/test_iso" does not exist.',
            ]
        )

    @patch('litp.metrics.set_handlers')
    def test_litp_plugins_empty(self, mock_set_handlers):
        self.mockfs.mount_directory('/tmp/test_iso/litp/plugins')
        self.importer = IsoImporter('/tmp/test_iso', 'ms1', ['node1', 'node2'])
        call_data = [
            {
                'method': 'run_puppet',
                'in': {
                    'agent': 'puppet',
                    'action': 'disable',
                    'nodes': ['ms1', 'node1', 'node2'],
                    'action_kwargs': None
                },
                'out': self._good_rpc_result(['ms1', 'node1', 'node2'])
            },
            {
                'method': 'run_rpc_command',
                'in': {
                    'agent': 'packagesimport',
                    'action': 'rsync_packages',
                    'nodes': ['ms1'],
                    'action_kwargs': {
                        'destination_path': '/var/www/html/litp',
                        'source_path': '/tmp/test_iso/litp/plugins/',
                        'import_appstream': str(False)
                    }
                },
                'out': self._good_rpc_result(['ms1'])
            },
            {
                'method': 'run_rpc_command',
                'in': {
                    'agent': 'packagesimport',
                    'action': 'create_repo',
                    'nodes': ['ms1'],
                    'action_kwargs': {
                        'destination_path': '/var/www/html/litp'
                    }
                },
                'out': self._good_rpc_result(['ms1'])
            },
            {
                'method': 'run_rpc_command',
                'in': {
                    'agent': 'packagesimport',
                    'action': 'clean_yum_cache',
                    'nodes': ['node1', 'node2', 'ms1'],
                    'action_kwargs': None
                },
                'out': self._good_rpc_result(['ms1', 'node1', 'node2'])
            },
            {
                'method': 'run_puppet',
                'in': {
                    'agent': 'puppet',
                    'action': 'enable',
                    'nodes': ['ms1'],
                    'action_kwargs': None
                },
                'out': self._good_rpc_result(['ms1'])
            },
            {
                'method': 'run_puppet',
                'in': {
                    'agent': 'puppet',
                    'action': 'enable',
                    'nodes': ['node1', 'node2'],
                    'action_kwargs': None
                },
                'out': self._good_rpc_result(['node1', 'node2'])
            }
        ]

        self._set_expected_call_data(call_data)
        self._assert_import_success()
        self._set_expected_call_data(call_data)
        self._fake_statefile.stop()
        self._statefile = self._fake_statefile.start()
        with patch.object(PuppetCatalogRunProcessor, 'trigger_and_wait', MagicMock(side_effect=RpcExecutionException('oops'))):
            self._assert_import_failure(['oops'])

    @patch('os.fork', MagicMock(side_effect=OSError(2, 'uh oh')))
    @patch('sys.stderr', MagicMock())
    def test_fork_fails(self):
        self.assertRaises(ForkError,
                          run_detached_child, '/test/litp', ['arg1', 'arg2'])

    @patch('os.execv', MagicMock(side_effect=OSError(2, 'uh oh')))
    @patch('os.umask', MagicMock(return_value=True))
    @patch('os.setsid', MagicMock(return_value=True))
    @patch('os.chdir', MagicMock(return_value=True))
    @patch('os._exit', MagicMock(return_value=True))
    @patch('os.fork', MagicMock(return_value=0))
    @patch('sys.exit', MagicMock(return_value=0))
    @patch('sys.stderr', MagicMock())
    def test_execv_fails(self):
        run_detached_child('/test/litp', ['arg1', 'arg2'])
        self._statefile.write_state.has_calls(
            call.write_state(self._statefile.STATE_FAILED))

    @patch('litp.metrics.set_handlers')
    def test_error_exceptions(self, mock_set_handlers):
        self.importer = IsoImporter('/tmp/test_iso', 'ms1', ['node1', 'node2'])
        self.importer._write_file = MagicMock()
        self.importer._exists = MagicMock(return_value=False)
        self.importer._open_file = MagicMock()
        self.importer._fchmod = MagicMock()
        self.importer._touch_sitepp_file = MagicMock()
        result = {'node1': {'errors': 'ola ke ase'},
                  'node2': {'errors': ''}
                  }
        self.assertEqual(['node1: ola ke ase'],
                         self.importer._result_to_error(result))
        self.assertEqual([],
                         self.importer._result_to_error(result, ignore='ke ase'))
