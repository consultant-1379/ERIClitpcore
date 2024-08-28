from litp.core import litpcrypt

import unittest
import StringIO

from mock import MagicMock, patch, call

class MockGID(object):
    def __init__(self):
        self.gr_gid = 1337


class LitpCryptCLITests(unittest.TestCase):
    def setUp(self):
        litpcrypt.getgrnam = lambda x: MockGID()

    def test_pad(self):
        message = "test_message"
        result = litpcrypt.pad(message)
        self.assertEquals(result, message + chr(3) * 4)

        message = " message 16 long"
        result = litpcrypt.pad(message)
        self.assertEquals(result, message)

    @patch('litp.core.litpcrypt.sys.exit')
    @patch('__builtin__.open')
    @patch('litp.core.litpcrypt.ConfigParser.SafeConfigParser')
    def test_run(self, mock_scp_class, mock_open, mock_exit):
        def _mock_open(file_path, mode):
            mock_context = MagicMock()
            mock_context.__enter__ = MagicMock()
            mock_context.__exit__ = MagicMock()
            return mock_context

        mock_open.side_effect = _mock_open

        def mock__encrypt(data):
            return "encrypted_data"

        def _mock_scp_get(section, option):
            if 'keyset' == section:
                return "mock_keyset_path"
            elif 'password' == section:
                return "mock_shadow_path"
            elif 'service' == section:
                return 'dfs'

        mock_scp = MagicMock(name='mock_SafeConfigParser')
        mock_scp.get.side_effect = _mock_scp_get
        mock_scp.set.return_value = None

        cli = litpcrypt.LitpCrypter()
        cli._encrypt = mock__encrypt

        cli.run(["set", "system", "marco", "passwd"])
        cli.run(["delete", "system", "marco"])

        self.assertTrue(True)

        cli = litpcrypt.LitpCrypter()
        cli._encrypt = mock__encrypt
        cli.run(["set", "system", "marco", "passwd"])
        cli.run(["delete", "system", "marco"])
        self.assertTrue(True)


    @patch('litp.core.litpcrypt.LitpCrypter._encrypt', MagicMock(return_value="encrypted_password"))
    @patch('__builtin__.open')
    @patch('litp.core.litpcrypt.ConfigParser.SafeConfigParser')
    def test_username_encoding(self, mock_scp_class, mock_open):
        def _mock_scp_get(section, option):
            if 'keyset' == section:
                return "mock_keyset_path"
            elif 'password' == section:
                return "mock_shadow_path"
            elif 'service' == section:
                return 'dfs'

        def _mock_scp_has_option(section, option):
            if 'plaintext_user' == option:
                return True
            else:
                return False

        def _mock_open(file_path, mode):
            mock_context = MagicMock()
            mock_context.__enter__ = MagicMock()
            mock_context.__exit__ = MagicMock()
            return mock_context

        mock_scp = MagicMock(name='mock_SafeConfigParser')
        mock_scp.get.side_effect = _mock_scp_get
        mock_scp.set.return_value = None
        mock_scp.has_option.side_effect = _mock_scp_has_option
        mock_scp_class.return_value = mock_scp

        mock_open.side_effect = _mock_open

        crypter = litpcrypt.LitpCrypter()
        self.assertEquals('mock_keyset_path', crypter.keyset)
        self.assertEquals('mock_shadow_path', crypter.password_file_path)

        args = MagicMock()
        args.service = 'arbitrary_service'
        args.user = ':=!@#$%^&*()_+'
        args.password = 'passw0rd'
        args.pass_prompt = None
        crypter.args = args

        # Happy path: There is no pre-existing plaintext username
        crypter.set_password(crypter.args)

        self.assertEquals(2, mock_scp.get.call_count)
        expected_calls = [
            call('keyset', 'path'),
            call('password', 'path'),
        ]
        mock_scp.get.assert_has_calls(expected_calls)

        self.assertEquals(1, mock_scp.has_option.call_count)
        mock_scp.has_option.assert_has_calls([
            call('arbitrary_service', ':=!@#$%^&*()_+')
        ])

        self.assertEquals(1, mock_scp.set.call_count)
        mock_scp.set.assert_has_calls([
            call('arbitrary_service', 'Oj0hQCMkJV4mKigpXys', 'encrypted_password')
        ])

        mock_scp.has_option.reset_mock()
        mock_scp.set.reset_mock()

        # Unhappy path: There *is* a pre-existing plaintext username
        args.user = 'plaintext_user'
        crypter.args = args
        crypter.set_password(crypter.args)

        self.assertEquals(1, mock_scp.has_option.call_count)
        mock_scp.remove_option.assert_has_calls([
            call('arbitrary_service', 'plaintext_user')
        ])
        # We'll remove the plaintext option and replace it with a
        # base64-encoded option
        self.assertEquals(1, mock_scp.remove_option.call_count)
        mock_scp.remove_option.assert_has_calls([
            call('arbitrary_service', 'plaintext_user')
        ])

        self.assertEquals(1, mock_scp.set.call_count)
        mock_scp.set.assert_has_calls([
            call('arbitrary_service', 'cGxhaW50ZXh0X3VzZXI', 'encrypted_password')
        ])

    @patch('sys.exit', MagicMock(return_value=None))
    @patch('__builtin__.open')
    @patch('litp.core.litpcrypt.ConfigParser.SafeConfigParser')
    def test_username_deletion(self, mock_scp_class, mock_open):
        def _mock_scp_get(section, option):
            if 'keyset' == section:
                return "mock_keyset_path"
            elif 'password' == section:
                return "mock_shadow_path"

        def _mock_scp_has_option(section, option):
            # This is the B64-encoded special character username
            if 'Oj0hQCMkJV4mKigpXys' == option:
                return True
            # This is the B64-encoded 'plaintext' username
            elif 'cGxhaW50ZXh0X3VzZXI' == option:
                return False
            elif 'plaintext_user' == option:
                return True
            else:
                return False

        def _mock_open(file_path, mode):
            mock_context = MagicMock()
            mock_context.__enter__ = MagicMock()
            mock_context.__exit__ = MagicMock()
            return mock_context

        mock_scp = MagicMock(name='mock_SafeConfigParser')
        mock_scp.get.side_effect = _mock_scp_get
        mock_scp.set.return_value = None
        mock_scp.remove_option.return_value = None
        mock_scp.has_option.side_effect = _mock_scp_has_option
        mock_scp_class.return_value = mock_scp

        mock_open.side_effect = _mock_open

        crypter = litpcrypt.LitpCrypter()
        self.assertEquals('mock_keyset_path', crypter.keyset)
        self.assertEquals('mock_shadow_path', crypter.password_file_path)

        args = MagicMock()
        args.service = 'arbitrary_service'
        args.user = ':=!@#$%^&*()_+'
        crypter.args = args

        # Happy path: The username is found and is B64-encoded
        crypter.delete_password(crypter.args)

        self.assertEquals(2, mock_scp.get.call_count)
        expected_calls = [
            call('keyset', 'path'),
            call('password', 'path'),
        ]
        mock_scp.get.assert_has_calls(expected_calls)

        self.assertEquals(2, mock_scp.has_option.call_count)
        mock_scp.has_option.assert_has_calls([
            call('arbitrary_service', 'Oj0hQCMkJV4mKigpXys'),
            call('arbitrary_service', 'Oj0hQCMkJV4mKigpXys'),
        ])

        self.assertEquals(1, mock_scp.remove_option.call_count)
        mock_scp.remove_option.assert_has_calls([
            call('arbitrary_service', 'Oj0hQCMkJV4mKigpXys')
        ])

        mock_scp.has_option.reset_mock()
        mock_scp.remove_option.reset_mock()

        # Unhappy path: The username is present in plaintext
        args.user = 'plaintext_user'
        crypter.args = args
        crypter.delete_password(crypter.args)

        self.assertEquals(3, mock_scp.has_option.call_count)
        mock_scp.has_option.assert_has_calls([
            call('arbitrary_service', 'cGxhaW50ZXh0X3VzZXI'),
            call('arbitrary_service', 'plaintext_user'),
            call('arbitrary_service', 'cGxhaW50ZXh0X3VzZXI'),
        ])

        # We'll remove the plaintext option
        self.assertEquals(1, mock_scp.remove_option.call_count)
        mock_scp.remove_option.assert_has_calls([
            call('arbitrary_service', 'plaintext_user')
        ])

    @patch('sys.exit', MagicMock(return_value=None))
    @patch('litp.core.litpcrypt.LitpCrypter._encrypt', MagicMock(return_value="encrypted_password"))
    @patch('__builtin__.open')
    @patch('litp.core.litpcrypt.ConfigParser.SafeConfigParser')
    def test_run_prompt(self, mock_scp_class, mock_open):
        cli = litpcrypt.LitpCrypter()

        def _mock_open(file_path, mode):
            mock_context = MagicMock()
            mock_context.__enter__ = MagicMock()
            mock_context.__exit__ = MagicMock()
            return mock_context

        mock_open.side_effect = _mock_open
        mock_getpass = MagicMock(return_value="test_password")
        with patch("getpass.getpass", mock_getpass):
            cli.run(["set", "system", "marco", "--prompt"])

        mock_getpass.called_once_with(call('Confirm password:'))

    @patch('litp.core.litpcrypt.sys.exit')
    @patch('litp.core.litpcrypt.sys.stderr', MagicMock(return_value=StringIO.StringIO()))
    @patch('litp.core.litpcrypt.LitpCrypter._encrypt', MagicMock(side_effect=IOError))
    @patch('__builtin__.open')
    @patch('litp.core.litpcrypt.ConfigParser.SafeConfigParser')
    def test_run_exception(self, mock_scp_class, mock_open, mock_exit):

        def _mock_scp_get(section, option):
            if 'keyset' == section:
                return "mock_keyset_path"
            elif 'password' == section:
                return "mock_shadow_path"

        mock_scp = MagicMock(name='mock_SafeConfigParser')
        mock_scp.get.side_effect = _mock_scp_get
        mock_scp_class.return_value = mock_scp

        cli = litpcrypt.LitpCrypter()

        def _mock_open(file_path, mode):
            mock_context = MagicMock()
            mock_context.__enter__ = MagicMock()
            mock_context.__exit__ = MagicMock()
            return mock_context

        mock_open.side_effect = _mock_open
        cli.run(["set", "system", "marco", "passwd"])
        mock_exit.assert_called_once_with(1)


    @patch('litp.core.litpcrypt.sys.stderr', MagicMock(return_value=StringIO.StringIO()))
    @patch('litp.core.litpcrypt.sys.exit')
    @patch('__builtin__.open')
    @patch('litp.core.litpcrypt.ConfigParser.SafeConfigParser')
    def test_remove_no_section_no_option(self, mock_scp_class, mock_open, mock_exit):

        def _mock_scp_get(section, option):
            if 'keyset' == section:
                return "mock_keyset_path"
            elif 'password' == section:
                return "mock_shadow_path"

        def _mock_scp_has_option(section, option):
            # This is 'bad_user', b64-encoded
            if 'YmFkX3VzZXI' == option:
                return False
            elif 'bad_user' == option:
                return False
            return True

        def _mock_scp_has_section(option):
            if 'bad_service' == option:
                return False
            return True

        mock_scp = MagicMock(name='mock_SafeConfigParser')
        mock_scp.get.side_effect = _mock_scp_get
        mock_scp.set.return_value = None
        mock_scp.has_option.side_effect = _mock_scp_has_option
        mock_scp.has_section.side_effect = _mock_scp_has_section
        mock_scp_class.return_value = mock_scp

        cli = litpcrypt.LitpCrypter()
        #self.assertRaises(SystemExit, cli.run, ["delete", "bad_service", "bad_user"])
        cli.run(["delete", "bad_service", "bad_user"])
        mock_scp.has_section.assert_has_calls([call("bad_service")])
        mock_exit.assert_called_once_with(1)

        mock_exit.reset_mock()
        mock_scp.has_section.reset_mock()
        mock_scp.has_option.reset_mock()

        cli.run(["delete", "good_service", "bad_user"])
        mock_scp.has_section.assert_has_calls([call("good_service")])
        # delete_password() will check b64 first and plaintext second
        mock_scp.has_option.assert_has_calls([call("good_service", "YmFkX3VzZXI")])
        mock_scp.has_option.assert_has_calls([call("good_service", "bad_user")])
        mock_exit.assert_called_once_with(1)

    @patch('litp.core.litpcrypt.sys.exit')
    @patch('litp.core.litpcrypt.sys.stderr')
    @patch('litp.core.litpcrypt.ConfigParser.SafeConfigParser')
    def test_argument_check(self, mock_scp_class, mock_stderr, mock_exit):
        def _mock_scp_get(section, option):
            if 'keyset' == section:
                return "mock_keyset_path"
            elif 'password' == section:
                return "mock_shadow_path"

        mock_scp = MagicMock(name='mock_SafeConfigParser')
        mock_scp.get.side_effect = _mock_scp_get
        mock_scp_class.return_value = mock_scp

        cli = litpcrypt.LitpCrypter()

        cli.run(["set", "system", "", ""])
        #assert False, mock_stderr.write.mock_calls
        mock_exit.assert_called_with(1)
        mock_stderr.write.assert_has_calls([call('Error: password must not be empty\n')])
        mock_stderr.write.assert_has_calls([call('Error: user must not be empty\n')])

        cli.run(["delete", "", ""])
        mock_exit.assert_called_with(1)
        mock_stderr.write.assert_has_calls([call('Error: password must not be empty\n')])
        mock_stderr.write.assert_has_calls([call('Error: user must not be empty\n')])
