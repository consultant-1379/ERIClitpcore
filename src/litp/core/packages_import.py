##############################################################################
# COPYRIGHT Ericsson AB 2013
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################

import re
import os
import platform
from os import listdir
from os.path import exists, isdir
from abc import ABCMeta, abstractproperty
from string import replace
from litp.core.validators import ValidationError
from litp.core.constants import INTERNAL_SERVER_ERROR
from litp.core.litp_logging import LitpLogger
from litp.core.rpc_commands import RpcCommandProcessorBase,\
                                   reduce_errs
from litp.core.callback_api import CallbackApi
from litp.core.exceptions import RpcExecutionException
from litp.core.iso_import import RepoPathChecker


log = LitpLogger()


def get_ms_os_major_version():
    # return OS major version number
    _, version, _ = platform.linux_distribution()
    return version[0]

MS_OS_MAJOR_VERSION = get_ms_os_major_version()

STATIC_PATH = {
    'litp': '/var/www/html/litp/',
    '3pp': '/var/www/html/3pp/',
    '3pp_rhel{0}'.format(MS_OS_MAJOR_VERSION):
                '/var/www/html/3pp_rhel{0}/'.format(MS_OS_MAJOR_VERSION),
    'os': '/var/www/html/{0}/os/x86_64/Packages'.format(MS_OS_MAJOR_VERSION),
    'updates': '/var/www/html/{0}/updates/x86_64/Packages'.format(
                                                        MS_OS_MAJOR_VERSION)
}

VERSION_FILE = '.version'
VERSION_FILE_NEXT = '.version.next'


class ModelProxy(object):

    def __init__(self, model_manager):
        self._model_manager = model_manager

    @property
    def model_manager(self):
        return self._model_manager

    def query(self, item_path):
        """ Query model manager """
        return self.model_manager.get_item(item_path)

    def _ms_nodes(self):
        """ Get list of ms node """
        return [item for item in self.model_manager.get_all_nodes() if
                item._extends("ms")]

    def get_ms_node(self):
        """ Get ms node """
        return [self._ms_nodes()[0].hostname]

    def get_all_nodes(self):
        """ Get all nodes """
        return [node.hostname for node in self.model_manager.get_all_nodes() if
                not (node.is_initial() or node.is_for_removal())
        ]


class PackagesImport(object):
    """ Import packages to the repository """

    def __init__(self, source_path, destination_path, execution_manager):
        self.source_path = SourcePath(source_path)
        self.destination_path = DestinationPath(destination_path,
                    RepoPathChecker(execution_manager.model_manager))
        self.execution_manager = execution_manager
        self.model_manager = ModelProxy(self.execution_manager.model_manager)
        self.base_rpc_command_proc = RpcCommandProcessorBase()
        self.import_appstream = False

    @property
    def _paths_errors(self):
        """ Collect errors from path validator """
        return [error for error in (
            self.source_path.error,
            self.destination_path.error
        ) if error is not None]

    def _is_modules_in_appstream(self):
        """
        This method checks existence of modules.yaml.gz in AppStream.
        It also creates updates_AppStream path if doesn't exist.

        :returns: True or False
        """
        modules_yaml = []
        for _, _, files in os.walk(str(self.source_path)):
            modules_yaml = [_file for _file in files \
                            if _file.endswith("modules.yaml.gz")]
            if modules_yaml:
                break

        if not os.path.exists(str(self.destination_path)) \
        and modules_yaml:
            os.makedirs(str(self.destination_path))

        return bool(modules_yaml)

    def _is_src_appstream(self):
        """
        This method checks for appstream path from
        source Path

        :returns: True or False
        """
        spath = str(self.source_path)
        regexp = r'^RHEL[0-9]{1,2}.[0-9]{1,2}_AppStream-[0-9]+.[0-9]+.[0-9]+$'

        for token in spath.split(os.path.sep):
            if re.search(regexp, token):
                return True

        return False

    def run_import(self):
        """ Run packages import """

        if self._is_src_appstream():
            self.import_appstream = self._is_modules_in_appstream()
            if not self.import_appstream:
                log.trace.error('Failed to find modules.yaml.gz in %s' \
                                % self.source_path)
                return [ValidationError(
                        item_path='/import',
                        error_message="Path %s is not valid AppStream path"
                        % self.source_path)]

        if not self._paths_errors:
            ms_node = self.model_manager.get_ms_node()
            all_nodes = self.model_manager.get_all_nodes()

            execution_data = [(self._rsync_packages, ms_node)] \
                              if self.import_appstream else \
                              [(self._rsync_packages, ms_node), \
                              (self._create_repo, ms_node), \
                              (self._clean_yum_cache, all_nodes)]

            for method, arg in execution_data:
                errors = method(arg)
                if errors:
                    log.trace.error('Failure: %s' % errors)
                    return errors
        else:
            log.trace.error('Failure: Paths are invalid.')
            return self._paths_errors

    def _add_default_msg_to_errors(self, errors):
        # checks errors list and, if any of them is an empty string,
        # puts a generic error to improve usability
        msg = 'Received a non-zero exit code, but the error'\
              ' message is empty'
        return [e if e else msg for e in errors]

    def _rsync_packages(self, node):
        """ Run rsync by mco agent"""

        log.trace.info('Running rsync packages.')

        action_kwargs = {
            'source_path': self.source_path.abs_path,
            'destination_path': self.destination_path.abs_path,
            'import_appstream': str(self.import_appstream)
        }
        try:
            _, errors = self.base_rpc_command_proc.\
                            execute_rpc_and_process_result(
                            CallbackApi(self.execution_manager),
                            node,
                            'packagesimport',
                            'rsync_packages',
                            action_kwargs,
                            timeout=120,
                            retries=2
            )
        except RpcExecutionException as e:
            raise Exception(e)
        if errors:
            return [ValidationError(error_type=INTERNAL_SERVER_ERROR,
                    item_path='/import',
                    error_message="rsync failed with message: %s" % \
                            ', '.join(reduce_errs(errors)))]

    def _clean_yum_cache(self, nodes):
        """ Clean yum cache """

        log.trace.info('Running clean yum cache.')
        try:
            _, errors = self.base_rpc_command_proc.\
                        execute_rpc_and_process_result(
                            CallbackApi(self.execution_manager),
                            nodes,
                            'packagesimport',
                            'clean_yum_cache'

            )
        except RpcExecutionException as e:
            raise Exception(e)
        if errors:
            return [ValidationError(error_type=INTERNAL_SERVER_ERROR,
                        item_path='/import',
                        error_message="clean cache failed with message: %s" %
                        (error))
                    for error in self.\
                    _add_default_msg_to_errors(reduce_errs(errors))]

    def _create_repo(self, node):

        log.trace.info('Creating yum repo.')

        action_kwargs = {
            'destination_path': self.destination_path.abs_path
        }

        try:
            _, errors = self.base_rpc_command_proc.\
                        execute_rpc_and_process_result(
                            CallbackApi(self.execution_manager),
                            node,
                            'packagesimport',
                            'create_repo',
                            action_kwargs,
                            timeout=300
            )
        except RpcExecutionException as e:
            raise Exception(e)
        if errors:
            return [ValidationError(error_type=INTERNAL_SERVER_ERROR,
                        item_path='/import',
                        error_message="createrepo failed with message: %s" %
                        (error))
                    for error in self.\
                    _add_default_msg_to_errors(reduce_errs(errors))]

    def __repr__(self):
        return "<PackagesImport - {0} - {1} >".format(
            self.source_path.abs_path,
            self.destination_path.abs_path
        )


class Path(object):
    """ Abstract class for Paths objects """
    ___metaclass__ = ABCMeta

    def __init__(self, checker=None):
        if checker is None:
            checker = RepoPathChecker()
        self.checker = checker

    @abstractproperty
    def abs_path(self):
        pass

    @abs_path.setter
    def abs_path(self, path):
        pass

    @abs_path.getter
    def abs_path(self):
        pass

    def is_valid(self):
        validator = PathValidator(self)
        return True if validator.validate() else False

    @property
    def error(self):
        return None if self.is_valid() else \
                ValidationError(
                    item_path='/import',
                    error_message="Path %s is not valid"
                    % self.abs_path
                )

    def __str__(self):
        return "%s" % self.abs_path

    def __repr__(self):
        return "<Path - %s >" % self.abs_path


class DestinationPath(Path):
    """ Destination path """

    def __init__(self, path, checker=None):
        super(DestinationPath, self).__init__(checker)
        try:
            cleaned_path = replace(path, '-', '')
            try:
                self._abs_path = STATIC_PATH[cleaned_path]
            except KeyError:
                self._abs_path = path
        except AttributeError:
            self._abs_path = path

    @property
    def abs_path(self):
        return self._abs_path

    @abs_path.getter
    def abs_path(self):
        return self._abs_path


class SourcePath(Path):
    """ Source path """

    def __init__(self, path):
        super(SourcePath, self).__init__()

        try:
            if isdir(path) and not path.endswith('/'):
                self._abs_path = path + '/'
            else:
                self._abs_path = path
        except TypeError:
            self._abs_path = path

    @property
    def abs_path(self):
        return self._abs_path

    @abs_path.getter
    def abs_path(self):
        return self._abs_path


class PathValidator(object):
    """ Validator for UNIX path """

    REGEX_UNIX_PATH = re.compile("^(/)?([^/\0]+(/)?)+$")

    def __init__(self, path):
        self.path = path.abs_path
        self.path_cls = path
        self.checker = path.checker

    def validate(self):
        """ Validate path """

        result = [getattr(self, name)() for name in (
            '_path_exists', '_is_valid_path', '_checker_ok'
        )]

        if isinstance(self.path_cls, SourcePath):

            result.append(getattr(self, '_path_contains_rpm')())

        return not False in result

    def _is_valid_path(self):
        """ Check if unix path or file path"""
        return True if re.match(
            self.REGEX_UNIX_PATH,
            self.path
        ) else False

    def _path_exists(self):
        """ Check if path is a dir """
        return True if exists(self.path) else False

    def _checker_ok(self):
        """ Check if path is okay with the model """
        return self.checker.check_path(self.path) is None

    def _path_contains_rpm(self):
        """ Check is any rpm in path """
        try:
            if isdir(self.path):
                match = [f for f in listdir(self.path) if ".rpm" in f]
                return True if match else False
            else:
                return True if self.path.endswith(".rpm") else False

        except OSError:
            return False

    def __repr__(self):
        return "<PathValidator - %s >" % self.path
