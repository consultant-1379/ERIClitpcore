from litp.core import litpmsdbpwd
from litp.core.litpmsdbpwd import MSDBPwdSetter, PgPasswdHist, PgAuthid

import unittest
import StringIO
import os
from collections import namedtuple

from mock import MagicMock, patch, call, mock_open

class LitpMSDbPwdTests(unittest.TestCase):

    @patch('litp.core.litpmsdbpwd.sessionmaker')
    def test_get_passwd_hist(self, mock_sessionmaker):
        pwd_hist_list = []
        for num in xrange(4):
            pwd = PgPasswdHist()
            pwd.passwd = 'pwd{0}'.format(num)
            pwd_hist_list.append(pwd)

        mock_session = MagicMock()
        mock_session.query().order_by().limit.return_value = pwd_hist_list
        mock_sessionmaker.return_value = lambda: mock_session

        result = MSDBPwdSetter()._get_passwd_hist(5)
        self.assertEqual([pwd.passwd for pwd in pwd_hist_list], result)

    @patch('litp.core.litpmsdbpwd.sessionmaker')
    def test_get_current_password(self, mock_sessionmaker):
        pwd = PgAuthid()
        pwd.rolpassword = u'md538d6c314dd7df0e873eeb9f84f3e6784'

        mock_session = MagicMock()
        mock_session.query().filter().one.return_value = pwd
        mock_sessionmaker.return_value = lambda: mock_session

        result = MSDBPwdSetter()._get_current_password()
        self.assertEqual(pwd.rolpassword, result)

    @patch('litp.core.litpmsdbpwd.MSDBPwdSetter._get_passwd_hist')
    def test_validate_password(self, mock_get_hist):
        msdbpwdsetter = MSDBPwdSetter()
        mock_get_hist.return_value = \
                [msdbpwdsetter._md5_hash('Passw0rd' + str(i))
                 for i in xrange(5)]

        Test_Password = namedtuple('Test_Password', ['pwd', 'expected_ret'])
        test_pwds = [
            Test_Password('Pw0rd',     litpmsdbpwd.ERR_PASSWORD_INVALID),
            Test_Password('passw0rd',  litpmsdbpwd.ERR_PASSWORD_INVALID),
            Test_Password('PASSW0RD',  litpmsdbpwd.ERR_PASSWORD_INVALID),
            Test_Password('Password',  litpmsdbpwd.ERR_PASSWORD_INVALID),
            Test_Password('Passw0rd+', litpmsdbpwd.ERR_PASSWORD_INVALID),
            Test_Password('Postgres1', litpmsdbpwd.ERR_PASSWORD_INVALID),
            Test_Password('Passw0rd2', litpmsdbpwd.ERR_PWD_REPEAT),
            Test_Password('Passw0rd',  None)
        ]

        for test_pwd in test_pwds:
            msdbpwdsetter.passwd = test_pwd.pwd
            msdbpwdsetter.md5hash = msdbpwdsetter._md5_hash(test_pwd.pwd)
            err_msg = msdbpwdsetter._validate_password()
            self.assertEqual(test_pwd.expected_ret, err_msg)

    @patch('sys.stderr', new_callable=StringIO.StringIO)
    @patch('litp.core.litpmsdbpwd.MSDBPwdSetter._get_passwd_hist')
    @patch('litp.core.litpmsdbpwd.MSDBPwdSetter._get_current_password')
    def test_can_accept_new_password_pending(self, mock_get_curr,
                                             mock_get_hist, mock_stderr):
        msdbpwdsetter = MSDBPwdSetter()
        mock_get_curr.return_value = msdbpwdsetter._md5_hash('Passw0rd2')
        mock_get_hist.return_value = [msdbpwdsetter._md5_hash('Passw0rd3')]

        result = msdbpwdsetter._can_accept_new_password()
        self.assertEqual(False, result)
        self.assertEqual('\n' + litpmsdbpwd.WARN_PWD_UPDATE_PENDING + '\n',
                         mock_stderr.getvalue())

    @patch('litp.core.litpmsdbpwd.sys.stdout', new_callable=StringIO.StringIO)
    @patch('litp.core.litpmsdbpwd.sys.stderr', new_callable=StringIO.StringIO)
    @patch('getpass.getpass')
    @patch('litp.core.litpmsdbpwd.MSDBPwdSetter._get_passwd_hist')
    @patch('litp.core.litpmsdbpwd.MSDBPwdSetter._get_current_password')
    def test_can_accept_new_password_mismatch(self, mock_get_curr,
                                              mock_get_hist, mock_getpass,
                                              mock_stderr, mock_stdout):
        msdbpwdsetter = MSDBPwdSetter()
        mock_get_curr.return_value = msdbpwdsetter._md5_hash('Passw0rd3')
        mock_get_hist.return_value = [msdbpwdsetter._md5_hash('Passw0rd3')]
        mock_getpass.side_effect = ['Passw0rd0', 'Passw0rd1', 'Passw0rd2']

        result = msdbpwdsetter._can_accept_new_password()
        self.assertEqual(False, result)
        self.assertEqual('', mock_stderr.getvalue())
        self.assertEqual('\n'.join([litpmsdbpwd.WARN_CURR_PWD_MISMATCH] * 3) + '\n',
                         mock_stdout.getvalue())

    @patch('litp.core.litpmsdbpwd.sys.stdout', new_callable=StringIO.StringIO)
    @patch('litp.core.litpmsdbpwd.sys.stderr', new_callable=StringIO.StringIO)
    @patch('getpass.getpass')
    @patch('litp.core.litpmsdbpwd.MSDBPwdSetter._get_passwd_hist')
    @patch('litp.core.litpmsdbpwd.MSDBPwdSetter._get_current_password')
    def test_can_accept_new_password_hist_empty(self, mock_get_curr,
                                                mock_get_hist, mock_getpass,
                                                mock_stderr, mock_stdout):
        msdbpwdsetter = MSDBPwdSetter()
        mock_get_curr.return_value = msdbpwdsetter._md5_hash('Passw0rd3')
        mock_get_hist.return_value = []
        mock_getpass.return_value = 'Passw0rd3'

        result = msdbpwdsetter._can_accept_new_password()
        self.assertEqual(True, result)
        self.assertEqual('', mock_stderr.getvalue())
        self.assertEqual('', mock_stdout.getvalue())

    @patch('litp.core.litpmsdbpwd.sys.stdout', new_callable=StringIO.StringIO)
    @patch('litp.core.litpmsdbpwd.sys.stderr', new_callable=StringIO.StringIO)
    @patch('getpass.getpass')
    @patch('litp.core.litpmsdbpwd.MSDBPwdSetter._get_passwd_hist')
    @patch('litp.core.litpmsdbpwd.MSDBPwdSetter._get_current_password')
    def test_can_accept_new_password_match(self, mock_get_curr,
                                           mock_get_hist, mock_getpass,
                                           mock_stderr, mock_stdout):
        msdbpwdsetter = MSDBPwdSetter()
        mock_get_curr.return_value = msdbpwdsetter._md5_hash('Passw0rd3')
        mock_get_hist.return_value = [msdbpwdsetter._md5_hash('Passw0rd3')]
        mock_getpass.return_value = 'Passw0rd3'

        result = msdbpwdsetter._can_accept_new_password()
        self.assertEqual(True, result)
        self.assertEqual('', mock_stderr.getvalue())
        self.assertEqual('', mock_stdout.getvalue())

    @patch('litp.core.litpmsdbpwd.sys.stdout', new_callable=StringIO.StringIO)
    @patch('litp.core.litpmsdbpwd.sys.stderr', new_callable=StringIO.StringIO)
    @patch('getpass.getpass')
    def test_get_new_password(self, mock_getpass, mock_stderr, mock_stdout):
        mock_getpass.side_effect = ['', 'Passw0rd', 'Password',
                                    'Password', 'Password']

        result = MSDBPwdSetter()._get_new_password()
        self.assertEqual('Password', result)
        self.assertEqual('', mock_stderr.getvalue())
        self.assertEqual('\n'.join([litpmsdbpwd.WARN_EMPTY_PASSWORD,
                                    litpmsdbpwd.WARN_PWD_MISMATCH]) + '\n',
                         mock_stdout.getvalue())

    @patch('litp.core.litpmsdbpwd.sys.stdout', new_callable=StringIO.StringIO)
    @patch('litp.core.litpmsdbpwd.sys.stderr', new_callable=StringIO.StringIO)
    @patch('getpass.getpass')
    def test_get_new_password_max_retries(self, mock_getpass, mock_stderr,
                                          mock_stdout):
        mock_getpass.side_effect = ['Passw0rd', 'Password',
                                    'Passw0rd', 'Password',
                                    'Passw0rd', 'Password']

        result = MSDBPwdSetter()._get_new_password()
        self.assertEqual(None, result)
        self.assertEqual('', mock_stderr.getvalue())
        self.assertEqual('\n'.join([litpmsdbpwd.WARN_PWD_MISMATCH] * 3) + '\n',
                         mock_stdout.getvalue())

    @patch('os.fchown')
    @patch('grp.getgrnam')
    @patch('cherrypy.config.get')
    def test_write_password_to_manifest(self, mock_config_get, mock_getgrpnam,
                                        mock_fchown):
        mock_config_get.return_value = 'litp_root'
        m = mock_open()
        with patch('__builtin__.open', m, create=True):
            msdbpwdsetter = MSDBPwdSetter()
            msdbpwdsetter.md5hash = msdbpwdsetter._md5_hash('Passw0rd')
            result = msdbpwdsetter._write_password_to_manifest()

        self.assertEqual(call(os.path.join('litp_root',
                                           litpmsdbpwd.PP_MODULE_DIR,
                                           litpmsdbpwd.PP_FILE), 'w'),
                         m.call_args)
        self.assertEqual(call(litpmsdbpwd.PP_FILE_TEMPLATE.format(
                              msdbpwdsetter.md5hash)),
                         m().write.call_args)

    @patch('os.fchown')
    @patch('grp.getgrnam')
    @patch('cherrypy.config.get')
    @patch('litp.core.litpmsdbpwd.sessionmaker')
    @patch('getpass.getpass')
    @patch('litp.core.litpmsdbpwd.MSDBPwdSetter._get_passwd_hist')
    @patch('litp.core.litpmsdbpwd.MSDBPwdSetter._get_current_password')
    def test_password_set(self, mock_get_curr, mock_get_hist, mock_getpass,
                          mock_sessionmaker, mock_config_get, mock_getgrnam,
                          mock_fchown):
        msdbpwdsetter = MSDBPwdSetter()
        mock_get_curr.return_value = msdbpwdsetter._md5_hash('Passw0rd3')
        mock_get_hist.return_value = [msdbpwdsetter._md5_hash('Passw0rd3')]
        mock_getpass.side_effect = ['Passw0rd3', 'NewPassw0rd', 'NewPassw0rd']

        mock_session = MagicMock()
        mock_sessionmaker.return_value = lambda: mock_session
        mock_config_get.return_value = 'litp_root'

        m = mock_open()
        with patch('__builtin__.open', m, create=True):
            result = msdbpwdsetter._password_set()

        self.assertTrue(result)


    @patch('litp.core.litpmsdbpwd.os.getuid')
    @patch('litp.core.litpmsdbpwd.sys.stderr', new_callable=StringIO.StringIO)
    @patch('litp.core.litpmsdbpwd.sys.stdout', new_callable=StringIO.StringIO)
    @patch('litp.core.litpmsdbpwd.MSDBPwdSetter._password_set')
    @patch('litp.core.litpmsdbpwd.MSDBPwdSetter._setup_db_sessions')
    def test_run(self, mock_setup_db, mock_pwd_set,
                 mock_stdout, mock_stderr, mock_getuid):
        mock_getuid.return_value = 0
        result = MSDBPwdSetter().run(args=[])
        self.assertEqual(0, result)

        try:
            result = MSDBPwdSetter().run(args=['-h'])
        except SystemExit as e:
            self.assertEqual(e.code, 0)
        self.assertTrue('usage: ' in mock_stdout.getvalue())

        try:
            result = MSDBPwdSetter().run(args=['-x'])
        except SystemExit as e:
            self.assertEqual(e.code, 2)
        self.assertTrue('usage: ' in mock_stdout.getvalue())
        self.assertTrue('unrecognized arguments: -x' in mock_stderr.getvalue())


    @patch('cherrypy.config.update')
    @patch('litp.core.litpmsdbpwd.sessionmaker.configure')
    @patch('litp.core.litpmsdbpwd.create_engine')
    def test_setup_db_sessions(self, mock_create_engine, mock_session, mock_config_update):
        sql_alchemy_url = "postgresql+psycopg2://litp@'ms1':'5432'/litp?sslmode=verify-full"
        sql_alchemy_pg_url = "postgresql+psycopg2://litp@'ms1':'5432'/postgres?sslmode=verify-full"

        def get_url(url):
            return sql_alchemy_url if url == 'sqlalchemy.url' else sql_alchemy_pg_url

        pwd_setter = MSDBPwdSetter()
        pwd_setter.args = MagicMock()
        with patch("cherrypy.config.get", wraps=get_url) as mock_config_get:
          result = pwd_setter._setup_db_sessions()

        calls = [call("postgresql+psycopg2://litp@ms1:5432/litp?sslmode=verify-full"),
                 call("postgresql+psycopg2://litp@ms1:5432/postgres?sslmode=verify-full")]
        mock_create_engine.assert_has_calls(calls)
        self.assertTrue(result)
