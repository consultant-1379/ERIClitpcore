from litp.core.yum_upgrade import YumImport, \
    LITP_PLUGINS, LITP_3PP, LITP_UPDATES, LITP_OS, LITP_LITP, \
    YUM_LOCK_TIME

import unittest
from mock import MagicMock, patch
import yum.Errors
import time
import yum.rpmtrans
import traceback

real_rpmtrans_del = None

def patch_rpm_trans():
    # This function monkey-patches a wrapper around the __del__ method of
    # a class that would otherwise raise an exception when these tests are
    # run under Maven.  The exception is because a call is made to
    # rpm.setLogFile(sys.stderr), but sys.stderr is not a file when running
    # under maven, and rpm.setLogFile() (a method written in C) insists on
    # getting a real file, not just a file-like object.   Because the
    # exception is thrown in a __del__ method it is ignored, but a
    # worrying-looking warning is printed on stderr:
    #
    # Exception TypeError: TypeError('file object or None expected',) in
    #   <bound method RPMTransaction.new_del of
    #      <yum.rpmtrans.RPMTransaction instance at 0x36f62d8>> ignored
    #
    # We want to suppress that.

    global real_rpmtrans_del

    if real_rpmtrans_del is None:
        real_rpmtrans_del = yum.rpmtrans.RPMTransaction.__del__
        def new_del(self):
            try:
                real_rpmtrans_del(self)
            except TypeError as ex:
                if str(ex) != 'file object or None expected':
                    raise
        yum.rpmtrans.RPMTransaction.__del__ = new_del

class MockPkg(MagicMock):
    def __init__(self, pkg_name, repoid):
        super(MockPkg, self).__init__()
        self.name = pkg_name
        self.repoid = repoid


class TestYumApi(unittest.TestCase):
    def setUp(self):
        self.yi = YumImport()
        self.yi.doPackageLists = MagicMock()
        self.repos = [MagicMock(id=LITP_PLUGINS), MagicMock(id=LITP_3PP),
                      MagicMock(id=LITP_UPDATES),  MagicMock(id=LITP_OS),
                      MagicMock(id=LITP_LITP)]
        self.pkg_list = [MockPkg("foo_{0}".format(r.id), r.id) for r in self.repos]
        self.yi.repos.listEnabled = MagicMock(return_value=self.repos)
        self.yi.closeRpmDB = MagicMock()
        self.yi.close = MagicMock()
        self.old_pid = 215
        self.lock_error_msg = "Existing lock another app is running with pid %d" % self.old_pid
        self.os_error = OSError(200, "OSError occurred!")
        self.current_time = 1000
        patch_rpm_trans()

    def test_get_install_pkgs(self):
        self.yi._get_packages = MagicMock(return_value=self.pkg_list)
        self.assertEqual(set([self.pkg_list[0], self.pkg_list[-1]]),
                         set(self.yi.get_install_pkgs())
                         )

    def test_get_packages(self):
        names = ['ERIClitpmntrololo', 'ERIClitpmn', 'ERIClitpwat', 'sup']
        pkgs = [MockPkg(n, '') for n in names]
        self.assertEqual([pkgs[-2], pkgs[-1]], self.yi._get_packages(pkgs))

    def test_import_packages_fail_exception(self):
        self.yi.get_install_pkgs = MagicMock(return_value=self.pkg_list)
        self.yi.repos.listEnabled = MagicMock(return_value=self.repos)
        self.yi.doLock = MagicMock()
        self.yi.doUnlock = MagicMock()
        self.yi.install = MagicMock(side_effect=IndexError('Oh no I failed'))
        
        self.assertEqual(['Oh no I failed'], self.yi.import_packages())

    def test_import_packages_fail_resolveDeps_error(self):
        self.yi.get_install_pkgs = MagicMock(return_value=self.pkg_list)
        self.yi.repos.listEnabled = MagicMock(return_value=self.repos)
        self.yi.doLock = MagicMock()
        self.yi.doUnlock = MagicMock()
        self.yi.install = MagicMock()
        self.yi.repos.populateSack = MagicMock()
        self.yi.mark_updated_pkgs = MagicMock()
        self.yi.resolveDeps = MagicMock (return_value=(1, "Yum dependency failure"))

        self.assertEqual(['Yum dependency failure'], self.yi.import_packages())

    def test_import_packages_fail_buildTransaction_error(self):
        self.yi.get_install_pkgs = MagicMock(return_value=self.pkg_list)
        self.yi.repos.listEnabled = MagicMock(return_value=self.repos)
        self.yi.doLock = MagicMock()
        self.yi.doUnlock = MagicMock()
        self.yi.install = MagicMock()
        self.yi.repos.populateSack = MagicMock()
        self.yi.mark_updated_pkgs = MagicMock()
        self.yi.resolveDeps = MagicMock (return_value=(2,"Success"))
        self.yi.buildTransaction = MagicMock (return_value=(1,"Yum build transaction failure"))

        self.assertEqual(['Yum build transaction failure'], self.yi.import_packages())

    def test_import_packages(self):
        self.yi.get_install_pkgs = MagicMock(return_value=self.pkg_list)
        self.yi.repos.listEnabled = MagicMock(return_value=self.repos)
        self.yi.install = MagicMock()
        self.yi.doUnlock = MagicMock()
        self.yi.doLock = MagicMock()
        self.yi.repos.populateSack = MagicMock()
        self.yi.mark_updated_pkgs = MagicMock()
        self.yi.resolveDeps = MagicMock (return_value=(2,"Success"))
        self.yi.buildTransaction = MagicMock (return_value=(0,"Success, nothing to do"))
        self.yi.processTransaction = MagicMock()
        self.assertEqual([], self.yi.import_packages())

    def time_side_effect(self):
        self.current_time += 10
        return self.current_time

    def test__lock_yum(self):
        self.yi.doLock = MagicMock()
        self.assertEqual(None, self.yi._lock_yum())

    def test__lock_yum_fail(self):
        self.yi.doLock = MagicMock(side_effect=yum.Errors.LockError(0,
                                   self.lock_error_msg, self.old_pid))
        error_msg = "import_iso failed. Could not get yum lock after %d " \
                    "seconds" % YUM_LOCK_TIME
        with patch('time.time') as tt:
            tt.side_effect = self.time_side_effect
            self.assertEqual(error_msg, self.yi._lock_yum())

    def test__unlock_yum(self):
        self.yi.doUnLock = MagicMock()
        self.assertEqual(None, self.yi._unlock_yum())

    def test__unlock_yum_fail(self):
        save_doUnlock = self.yi.doUnlock
        self.yi.doUnlock = MagicMock(side_effect=self.os_error)
        try:
            self.assertEqual(str(self.os_error), self.yi._unlock_yum())
        finally:
            self.yi.doUnlock = save_doUnlock

    def test_import_packages_lock_yum_fails(self):
        self.yi.get_install_pkgs = MagicMock(return_value=self.pkg_list)
        self.yi.repos.listEnabled = MagicMock(return_value=self.repos)
        self.yi.doLock = MagicMock(side_effect=yum.Errors.LockError(1,
                                   self.lock_error_msg, self.old_pid))
        error_msg = "import_iso failed. Could not get yum lock after %d " \
                    "seconds" % YUM_LOCK_TIME
        with patch('time.time') as tt:
            tt.side_effect = self.time_side_effect
            self.assertEqual([error_msg], self.yi.import_packages())

    def test_import_packages_unlock_yum_fails(self):
        self.yi.get_install_pkgs = MagicMock(return_value=self.pkg_list)
        self.yi.repos.listEnabled = MagicMock(return_value=self.repos)
        self.yi.install = MagicMock()
        self.yi.doUnlock = MagicMock()
        self.yi.doLock = MagicMock()
        self.yi.repos.populateSack = MagicMock()
        self.yi.mark_updated_pkgs = MagicMock()
        self.yi.resolveDeps = MagicMock (return_value=(2,"Success"))
        self.yi.buildTransaction = MagicMock (return_value=(0,"Success, nothing to do"))
        save_doUnlock = self.yi.doUnlock
        self.yi.doUnlock = MagicMock(side_effect=self.os_error)
        self.yi.processTransaction = MagicMock()
        try:
            self.assertEqual([str(self.os_error)], self.yi.import_packages())
        finally:
            self.yi.doUnlock = save_doUnlock

    def test_import_packages_fail_exception_and_yum_unlock_fails(self):
        self.yi.get_install_pkgs = MagicMock(return_value=self.pkg_list)
        self.yi.repos.listEnabled = MagicMock(return_value=self.repos)
        self.yi.doLock = MagicMock()
        save_doUnlock = self.yi.doUnlock
        self.yi.doUnlock = MagicMock(side_effect=self.os_error)
        self.yi.install = MagicMock(side_effect=IndexError('Oh no I failed'))
        try:
            self.assertEqual(['Oh no I failed', str(self.os_error)], self.yi.import_packages())
        finally:
            self.yi.doUnlock = save_doUnlock
