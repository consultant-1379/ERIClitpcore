##############################################################################
# COPYRIGHT Ericsson AB 2013
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################


import yum
import re
from litp.core.litp_logging import LitpLogger
from litp.enable_metrics import apply_metrics
from yum import Errors
import time

RULES = {"exclude": {"LITP": "ERIClitpmn.*"},
         "include": {"LITP": "ERIClitp"}}
LITP_PLUGINS = "LITP_PLUGINS"
LITP_3PP = "3PP"
LITP_UPDATES = "UPDATES"
LITP_OS = "OS"
LITP_LITP = "LITP"
YUM_SUCCESS = [0, 2]
YUM_LOCK_TIME = 60

log = LitpLogger()


class PkgRules(object):
    def __init__(self, excl_rules, accept_rules):
        self.excl_rules = excl_rules
        self.accept_rules = accept_rules

    @classmethod
    def from_json(cls):
        return cls(RULES['exclude'], RULES['include'])


class YumImport(yum.YumBase):
    def __init__(self):
        yum.YumBase.__init__(self)
        self.pkgs = PkgRules.from_json()
        apply_metrics(self)

    def import_packages(self):
        """
        Should install the greater version of available and
        installed.
        """
        errors = []
        try:
            error_msg = self._lock_yum()
            if error_msg:
                errors.append(error_msg)
                return errors

            log.trace.info("Enabled repos: {0}".format(
                ', '.join([r.id for r in self.repos.listEnabled()]))
            )
            # Getting a list of packages that
            # are available in the LITP_PLUGINS repo
            litp_plug_pkgs = self.get_install_pkgs()
            pkgs_to_install = set([p.name for p in litp_plug_pkgs])
            for pkg in pkgs_to_install:
                log.trace.info("Asking yum to install/update package: " \
                               "%s " % pkg)
                self.install(name=pkg)
            # TODO: understand better what these pkgSacks do
            # fills self.pkgSack with the enabled repos. Needed to resolve
            # dependencies correctly. If you're not sure about which repos are
            # enabled the same method can be run passing 'all', which will fill
            # the sack with all repos and not only the enabled ones
            self.repos.populateSack()
            self.mark_updated_pkgs()

            result, msg = self.resolveDeps()
            log.trace.debug("Resolve dependencies returned: %d, %s "
                            % (result, msg))
            if result not in YUM_SUCCESS:
                log.event.error("import_iso encountered a yum dependency " \
                                "error.")
                errors.append(msg)
                return errors

            result, msg = self.buildTransaction()
            log.trace.debug("Build transaction returned: %d, %s "
                                    % (result, msg))
            if result not in YUM_SUCCESS:
                log.event.error("import_iso encountered a yum " \
                                    "transaction error.")
                errors.append(msg)
                return errors

            self.processTransaction()

        except Exception as e:  # pylint: disable=W0703
            log.event.error("import_iso encountered a yum error. Please " \
                            "check yum and ensure it is in a stable state. " \
                            "Yum must be in a stable state for import_iso " \
                            "to function.")
            errors.append(str(e))

        finally:
            error_msg = self._unlock_yum()
            if error_msg:
                errors.append(error_msg)
            return errors  # pylint: disable=W0150

    def get_install_pkgs(self):
        # available lists versions for both installed and uninstalled packages
        # this means that updates is a subset of available.
        all_pkgs = self._get_packages(self.doPackageLists('available'))
        # we only want to install stuff from litp repos
        return [p for p in all_pkgs if p.repoid in [LITP_LITP, LITP_PLUGINS]]

    def mark_updated_pkgs(self):
        # hopefully we shouldn't need doPackageLists to specify that we
        # want to narrow it do 'update', but we might have to
        return self.update()

    def _get_packages(self, pkgs):
        packages = []
        for pkg in pkgs:
            for k in self.pkgs.excl_rules:
                if not re.match(self.pkgs.excl_rules[k], pkg.name):
                    packages.append(pkg)

        return packages

    def _lock_yum(self):
        yum_get_lock_expire_time = time.time() + YUM_LOCK_TIME
        locked = False
        while time.time() <= yum_get_lock_expire_time:
            try:
                self.doLock()
                log.trace.debug("import_iso has obtained the yum lock")
                locked = True
                break
            except Errors.LockError:
                pass
        if not locked:
            error_msg = "import_iso failed. Could not get yum lock after " \
                        "%d seconds" % YUM_LOCK_TIME
            return error_msg

    def _unlock_yum(self):
        try:
            self.closeRpmDB()
            self.close()
            self.doUnlock()
            log.trace.debug("import_iso has released the yum lock")
        except Exception, e:  # pylint: disable=W0703
            log.trace.error("import_iso failed. An error occurred while " \
                            "trying to release the yum lock")
            return str(e)
