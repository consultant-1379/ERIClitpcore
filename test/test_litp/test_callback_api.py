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
from mock import MagicMock, patch, call
from litp.core.callback_api import CallbackApi
from litp.encryption.encryption import EncryptionAES
from litp.core.plan import Plan
from litp.core.model_manager import ModelManager, QueryItem
from litp.core.execution_manager import ExecutionManager
from litp.core.model_type import Property, Child, Reference
from litp.core.model_type import PropertyType
from litp.core.model_type import ItemType
from litp.core.model_item import ModelItem
from litp.core.rpc_commands import run_rpc_command
import ConfigParser


class MockModelManager(object):
    pass


class MockExecutionManager(object):
    def __init__(self, *args, **kwargs):
        self.model_manager = MockModelManager()


class MockJob(object):
    def __init__(self):
        self.processing = True


def mock_check_key(a, b):
    return False

def mock_check_key2(a, b):
    return True

class myReader(object):

    def read(self, file_path):
        return

    def get(self, file_path, key):
        return "test_value"

class MockItemValidator(object):
    def validate(self, properties):
        return self._validate(properties)

    @staticmethod
    def _validate(properties):
        if (14 < sum([len(value) for value in properties.values()])):
            return MagicMock(name="ValidationError")
        else:
            return None

class TestCallbackApi(TestCase):

    @patch('os.path.exists', MagicMock(return_value=True))
    def setUp(self):
        self.test_key_file = None
        self.model = ModelManager()
        self.model.register_property_type(PropertyType("basic_string"))
        self.model.register_property_type(PropertyType("integer", regex=r'[0-9]+'))
        self.model.register_item_type(
            ItemType(
                "foo",
                bar=Property("basic_string"),
                baz=Property("basic_string", updatable_plugin=True),
                qux=Reference("bar"),
                integer=Property("integer", updatable_plugin=True, required=True),
                validators=[MockItemValidator()],
            )
        )
        self.model.register_item_type(
            ItemType(
                "bar",
                name=Property("basic_string"),
            )
        )
        self.model.register_item_type(
            ItemType(
                "root",
                foo=Child("foo"),
                bar=Child("bar"),
            )
        )
        self.model.create_root_item("root")

        def mock_write_key(a, location, key):
            self.test_key_file = key

        EncryptionAES.check_key = mock_check_key
        EncryptionAES.write_key = mock_write_key

        self.execution = ExecutionManager(self.model, None, None)
        self.api = CallbackApi(self.execution)

    def tearDown(self):
        pass

    def test_property_update(self):
        self.model.create_item("foo", "/foo", bar="foobar", baz="foobaz", integer="42")
        self.model.create_item("bar", "/bar", name="Alice")
        self.model.create_inherited("/bar", "/foo/qux")

        item = self.api.query("foo")[0]
        self.assertTrue(item._updatable)

        # Property 'bar' is not plugin_updatable
        self.assertRaises(AttributeError, item.__setattr__,
                          "bar", "something_different")

        # Property 'baz' is
        item.baz = "raboof"

        root_qi = self.api.query("root")[0]
        self.assertTrue(root_qi._updatable)

        foo_item = root_qi.query("foo")[0]
        self.assertEquals(item.vpath, foo_item.vpath)
        self.assertTrue(foo_item._updatable)

        foo_parent_item = foo_item.get_parent()
        self.assertEquals(root_qi.vpath, foo_parent_item.vpath)
        self.assertTrue(foo_parent_item._updatable)

        self.assertTrue(item.qux._updatable)
        reference_item = item.query("bar")[0]
        self.assertTrue(reference_item._updatable)

        reference_source = reference_item.get_source()
        self.assertEquals("/bar", reference_source.vpath)
        self.assertTrue(reference_source._updatable)

    def test_property_update_applied_item(self):
        self.model.create_item("foo", "/foo", bar="foobar", baz="foobaz", integer="42")
        self.model.create_item("bar", "/bar", name="Alice")
        self.model.create_inherited("/bar", "/foo/qux")

        self.model.set_all_applied()

        item = self.api.query("foo")[0]
        self.assertTrue(item._updatable)

        # Property 'bar' is not plugin_updatable
        self.assertRaises(AttributeError, item.__setattr__,
                          "bar", "something_different")

        self.assertEquals(ModelItem.Applied, item.get_state())
        # Property 'baz' is
        item.baz = "raboof"
        self.assertEquals(ModelItem.Updated, item.get_state())

        root_qi = self.api.query("root")[0]
        self.assertTrue(root_qi._updatable)

        foo_item = root_qi.query("foo")[0]
        self.assertEquals(item.vpath, foo_item.vpath)
        self.assertTrue(foo_item._updatable)

        foo_parent_item = foo_item.get_parent()
        self.assertEquals(root_qi.vpath, foo_parent_item.vpath)
        self.assertTrue(foo_parent_item._updatable)

        self.assertTrue(item.qux._updatable)
        reference_item = item.query("bar")[0]
        self.assertTrue(reference_item._updatable)

        reference_source = reference_item.get_source()
        self.assertEquals("/bar", reference_source.vpath)
        self.assertTrue(reference_source._updatable)

    def test_query_by_vpath(self):
        self.model.create_item("foo", "/foo", bar="foobar", baz="foobaz", integer="42")

        item = self.api.query_by_vpath("/foo")
        self.assertTrue(isinstance(item, QueryItem))
        self.assertEqual('/foo', item.get_vpath())
        same_item = self.api.query("foo")[0]
        self.assertEqual(item, same_item)
        self.assertRaises(AttributeError, item.__setattr__,
                          "bar", "something_different")
        item.baz = "raboof"
        no_item = self.api.query_by_vpath("is/not/there")
        self.assertTrue(no_item == None)

    def test_property_validator_on_update(self):
        self.model.create_item("foo", "/foo", bar="foobar", baz="foobaz", integer="42")
        item = self.api.query("foo")[0]
        self.assertRaises(AttributeError, item.__setattr__, "integer", 'not_an_int')

    @patch('test_callback_api.MockItemValidator.validate')
    def test_item_validator_on_update(self, mock_item_validator):
        def item_validator(props):
            return MockItemValidator._validate(props)

        mock_item_validator.side_effect = item_validator
        self.model.create_item("foo", "/foo", bar="foobar", baz="foobaz", integer="43")
        self.assertEquals(1, mock_item_validator.call_count)
        item = self.api.query("foo")[0]
        setattr(item, 'integer', '43')
        self.assertEquals(2, mock_item_validator.call_count)
        self.assertRaises(AttributeError, item.__setattr__, "integer", '213')
        self.assertEquals(3, mock_item_validator.call_count)
        setattr(item, 'baz', 'fooba')
        self.assertEquals(4, mock_item_validator.call_count)
        setattr(item, 'integer', '213')
        self.assertEquals(5, mock_item_validator.call_count)


    def testPlanRunning(self):
        self.assertFalse(self.api.is_running())

        self.execution.plan = Plan([], [])
        self.execution.plan.set_ready()
        self.execution.plan.run()

        self.assertTrue(self.api.is_running())

    @patch('os.path.exists', MagicMock(return_value=True))
    @patch('litp.core.base_plugin_api.ConfigParser.SafeConfigParser')
    def test__create_keyset(self, mock_scp_class):

        mock_scp_class.return_value = myReader()
        execution_manager = MockExecutionManager()
        cba = CallbackApi(execution_manager)
        cba.initialize()

        result = self.test_key_file
        cba.initialize()

        self.assertNotEquals(result, self.test_key_file)

        EncryptionAES.check_key = mock_check_key2

        result = self.test_key_file
        cba.initialize()

        self.assertEquals(result, self.test_key_file)

    @patch('os.path.exists', MagicMock(return_value=True))
    @patch('litp.core.base_plugin_api.ConfigParser.SafeConfigParser')
    def test_username_encoding(self, mock_scp_class):
        # This will be use to mock the SafeConfigParser instance that reads the
        # LITP security config file as well as the SafeConfigParser used to
        # read the LITP shadow file
        def _mock_scp_get(section, option):
            if 'keyset' == section:
                return "mock_keyset_path"
            elif 'password' == section:
                return "mock_shadow_path"
            elif 'service' == section:
                if 'plaintext' == option:
                    return "encrypted_password"
                elif 'Y29sb246ZXF1YWw9Zm9v' == option:
                    return "other_encrypted_password"
                else:
                    raise ConfigParser.NoOptionError(option, section)

        def _mock_decrypt(key, encrypted_password):
            if 'encrypted_password' == encrypted_password:
                return 'cleartext_password'
            elif 'other_encrypted_password' == encrypted_password:
                return 'other_cleartext_password'

        # Set up mocking for SafeConfigParser
        mock_scp = MagicMock(name="mock_scp_class")
        mock_scp_class.return_value = mock_scp
        mock_scp.get = MagicMock(side_effect=_mock_scp_get)

        execution_manager = MockExecutionManager()
        api = CallbackApi(execution_manager)

        # Set up mocking for EncryptionAES
        api._security.aes = MagicMock()
        api._security.aes.read_key = MagicMock(return_value="encrypted_key")
        api._security.aes.decrypt = MagicMock(side_effect=_mock_decrypt)

        password = api.get_password("service", "plaintext")
        self.assertEquals("cleartext_password", password)

        # Since this is the first call to the callback api, we should have 4
        # calls to get: 2 to read the LITP security config file, one to
        # retrieve the encrypted password for the b64-encoded username and one
        # for the plaintext username
        self.assertEquals(4, mock_scp.get.call_count)
        expected_calls = [
                call('keyset', 'path'),
                call('password', 'path'),
                call('service', 'cGxhaW50ZXh0'),
                call('service', 'plaintext')
            ]
        mock_scp.get.assert_has_calls(expected_calls)

        mock_scp.get.reset_mock()
        password = api.get_password("service", "colon:equal=foo")
        self.assertEquals("other_cleartext_password", password)

        self.assertEquals(1, mock_scp.get.call_count)
        expected_calls = [
                call('service', 'Y29sb246ZXF1YWw9Zm9v')
            ]
        mock_scp.get.assert_has_calls(expected_calls)

    @patch('os.path.exists', MagicMock(return_value=True))
    @patch('litp.core.base_plugin_api.ConfigParser.SafeConfigParser')
    def test_get_password(self, mock_scp_class):
        class myReader(object):

            def read(self, file_path):
                return

            def get(self, file_path, key):
                return "test_value"

            def has_section(self, section):
                return True

            def add_section(self, section):
                return

            def remove_option(self, section, option):
                return

            def set(self, section, key, value):
                return

            def write(self, file_path):
                return

        class myAes(object):
            def read_key(self, file):
                return "mock key"

            def decrypt(self, key, encrypted):
                return "test_decrypted message"

        mock_scp_class.return_value = myReader()

        execution_manager = MockExecutionManager()
        cba = CallbackApi(execution_manager)

        cba._security.aes = myAes()

        password = cba.get_password("service", "user")

        self.assertEquals("test_decrypted message", password)

    @patch('os.path.exists', MagicMock(return_value=False))
    def test_error_with_no_file(self):
        execution_manager = MockExecutionManager()
        callback_api = CallbackApi(execution_manager)
        self.assertRaises(OSError, callback_api.get_password, "test", "test")

    @patch('os.path.exists', MagicMock(return_value=True))
    @patch('litp.core.rpc_commands._run_process')
    def test_run_rpc(self, mock_rpc):
        mock_rpc.return_value=('[]', "")
        cba = CallbackApi(MockExecutionManager())
        cba.rpc_command(['node'], 'agent', 'action', {}, 60)
        mock_rpc.assert_called_once_with(['mco', 'rpc', '--json', '--timeout=60', '-I', 'node', 'agent', 'action'])

    @patch('os.path.exists', MagicMock(return_value=True))
    def test_get_escaped_password(self):
        def mock_get_password(service, user):
            return """'pro/fi`le\"'"""
        self.api.get_password = mock_get_password

        escaped = self.api.get_escaped_password("my_service", "my_user")
        self.assertEqual("""\\'pro/fi\\`le\\\"\\'""", escaped)

        self.api.get_password = lambda s,u: '''Amm30n!!'''
        escaped = self.api.get_escaped_password("my_service", "my_user")
        self.assertEqual("""Amm30n\\!\\!""", escaped)
        # We're expecting 2 extra characters to escape the exclamation marks
        self.assertEqual(10, len(escaped))

        self.api.get_password = lambda s,u: '''~a b'c"d$e(f)g#h;i|j&k*l`m<n>o'''
        self.assertEqual(30, len(self.api.get_password("my_service", "my_user")))
        escaped = self.api.get_escaped_password("my_service", "my_user")
        self.assertEqual("""\\~a\\ b\\'c\\\"d\\$e\\(f\\)g\\#h\\;i\\|j\\&k\\*l\\`m\\<n\\>o""", escaped)
        self.assertEqual(45, len(escaped))

        self.api.get_password = lambda s,u: None
        escaped = self.api.get_escaped_password("my_service", "my_user")
        self.assertTrue(escaped is None)

    def test_sanitized_string(self):

        def test_escaping_and_length(expected, raw):
            self.assertEquals(expected, self.api.sanitize(raw))
            self.assertEquals(4, len(self.api.sanitize(raw)))

        # We're trying to make an arbitrary string shell-safe for use in CallbackTasks
        test_escaping_and_length('a\\\\b', '''a\\b''')
        test_escaping_and_length('a\\\'b', '''a'b''')
        test_escaping_and_length('a\\"b', '''a"b''')
        test_escaping_and_length('a\\`b', '''a`b''')
        test_escaping_and_length('a\\(b', '''a(b''')
        test_escaping_and_length('a\\)b', '''a)b''')
        test_escaping_and_length('a\\~b', '''a~b''')
        test_escaping_and_length('a\\!b', '''a!b''')
        test_escaping_and_length('a\\#b', '''a#b''')
        test_escaping_and_length('a\\>b', '''a>b''')
        test_escaping_and_length('a\\<b', '''a<b''')
        test_escaping_and_length('a\\ b', '''a b''')
        test_escaping_and_length('a\\$b', '''a$b''')
        test_escaping_and_length('a\\*b', '''a*b''')
        test_escaping_and_length('a\\|b', '''a|b''')
        test_escaping_and_length('a\\;b', '''a;b''')

        self.assertEquals('user\\\'\\!', self.api.sanitize('''user'!'''))
        self.assertEquals(8, len(self.api.sanitize('''user'!''')))

if __name__ == "__main__":

    unittest.main()
