import os
import sys
import logging
import time
import platform

from os import stat
import litp.metrics
from litp.core.litp_logging import LitpLogger
from litp.core.rpc_commands import NoStandardErrorRpcCommandProcessor, \
                                   run_rpc_command,\
                                   reduce_errs,\
                                   PuppetCatalogRunProcessor,\
                                   PuppetExecutionProcessor,\
                                   PuppetMcoProcessor
from litp.core.validators import ValidationError
from litp.core.model_item import ModelItem
from litp.core.maintenance import enter_maintenance_mode, StateFile
from litp.core.yum_upgrade import YumImport
from litp.core.exceptions import InvalidIsoException, RpcExecutionException,\
    ForkError
from litp.core.constants import INTERNAL_SERVER_ERROR
from litp.enable_metrics import apply_metrics
from litp.core.event_emitter import EventEmitter

UMASK = 022  # Turn off write permissions for g & o

log = LitpLogger()


class RepoPathChecker(object):
    """Class for checking if we are allowed update a Yum repository.

    Repositories referenced by os-profiles should be considered read-only.
    """
    def __init__(self, model_manager=None):
        # A RepoPathChecker created without a ModelManager will allow
        # any path, as though the model were empty.
        self._dirmap = {}
        if model_manager is not None:
            for profile in model_manager.query('os-profile'):
                self._dirmap[os.path.realpath(profile.path)] = \
                    profile.get_vpath()

    def check_path(self, path):
        """Return vpath of os-profile referencing path, if any."""
        realpath = os.path.realpath(path)
        return self._dirmap.get(realpath, None)


class IsoParser(object):
    """Understands LITP-compliant ISO Format"""

    VERB_VERIFY_CHECKSUM = "VERIFY_CHECKSUM"
    VERB_RSYNC_IMAGES = "RSYNC_IMAGES"
    VERB_GENERATE_CHECKSUM = "GENERATE_CHECKSUM"
    VERB_RSYNC_RPMS = "RSYNC_RPMS"
    VERB_CREATE_REPO = "CREATE_REPO"
    VERB_CLEAN_YUM_CACHE = "CLEAN_YUM_CACHE"
    VERB_INSTALL_RPMS = "INSTALL_RPMS"
    VERB_ENABLE_PUPPET = "ENABLE_PUPPET"
    VERB_DISABLE_PUPPET = "DISABLE_PUPPET"

    REPO_ROOT = '/var/www/html'

    def __init__(self, path, repo_path_checker=None):
        self._path = path
        self._valid = False
        self._errors = []
        self._actions = []
        self._images = {}
        self._imageswithoutmd5 = {}
        self._checksums = {}
        self._checksumdictempty = True
        self._checksumfillend = False
        if repo_path_checker is None:
            repo_path_checker = RepoPathChecker()
        self._repo_path_checker = repo_path_checker

    def _add_action(self, verb, args, append_at_end=True):
        log.trace.debug('Adding action: "%s" - %s' % (verb, args))
        actions = {
            'verb': verb,
            'args': args
        }
        if append_at_end:
            self._actions.append(actions)
        else:
            self._actions.insert(0, actions)

    def _add_error(self, msg):
        log.trace.debug('Adding error: "%s"' % msg)
        self._errors.append(msg)

    def _fatal_error(self, msg):
        self._add_error(msg)
        return self._errors

    def _iso_path(self, path):
        return os.path.join(self._path, path)

    def _check_repo(self, src, repo_name):

        log.trace.debug("checking for repo source: " + src)
        if os.path.exists(src):
            if os.path.isdir(src):
                for child in os.listdir(src):
                    child_path = os.path.join(src, child)
                    if os.path.isfile(child_path):
                        if child == 'comps.xml' or child[-4:] == '.rpm':
                            self._check_file_not_empty(child_path)
            else:
                self._add_error(
                    'Source path "%s" exists but is not a directory' % src)
            dst = os.path.join(self.REPO_ROOT, repo_name)
            log.trace.debug("checking for repo destination: " + dst)
            if os.path.exists(dst):
                if not os.path.isdir(dst):
                    self._add_error(
                    'Destination path "%s" exists but is not a directory' % \
                    dst)
            clashing_profile = self._repo_path_checker.check_path(dst)
            if clashing_profile:
                self._add_error(
                'Destination path "%s" clashes with os-profile "%s"' % \
                (dst, clashing_profile))
            # The rsync will create the directory if it does not exist
            # (provided that permissions and SELinux allow it).
            self._add_action(self.VERB_RSYNC_RPMS, {
                    "source": src,
                    "destination": dst,
            })
            self._add_action(self.VERB_CREATE_REPO, {
                    "directory": dst,
            })
        else:
            log.trace.debug("source path not found: " + src)

    def _check_file_not_empty(self, path):
        statinfo = stat(path)
        if statinfo.st_size == 0:
            self._add_error('File "%s" is of zero length.' % path)

    def _check_images(self, src, repo_name):
        log.trace.debug('Checking image directory "%s", destination "%s"' % \
                        (src, repo_name))
        if os.path.exists(src):
            if not os.path.isdir(src):
                self._add_error(
                    'Source path "%s" exists but is not a directory' % src)
                return
            # For the case of the images an error is returned if not found
            dst = os.path.join(self.REPO_ROOT, repo_name)

            for child in os.listdir(src):
                child_path = os.path.join(src, child)
                if child.endswith('.md5'):
                    # Child is an MD5 file (hopefully)
                    image_path = child_path[:-4]
                    log.trace.debug('child_path: "%s", image_path "%s"' % \
                                    (child_path, image_path))
                    if os.path.isfile(child_path):
                        self._check_file_not_empty(child_path)
                        if not os.path.exists(image_path):
                            self._add_error(
                                'Checksum file "%s" exists but image file '
                                '"%s" does not exist' % \
                                (child_path, image_path))
                        elif not os.path.isfile(image_path):
                            self._add_error(
                                'Image path "%s" exists but is not a file.' % \
                                image_path)
                        else:
                            self._images[image_path] = dst
                elif os.path.isfile(child_path):
                    self._check_file_not_empty(child_path)
                    # Child is an Image file (hopefully)
                    if not os.path.exists(child_path + '.md5'):
                        # There is no correspodning MD5 file
                        self._imageswithoutmd5[child_path] = dst

    def _validate_images(self):
        IMAGES_ROOT = 'images'

        # Check for VM images to load in repo
        src_dir = self._iso_path(IMAGES_ROOT)

        if os.path.exists(src_dir):
            log.trace.debug('Looking at : "%s"' % src_dir)
            if os.path.isdir(src_dir):
                self._check_images(src_dir, IMAGES_ROOT)
                for child in os.listdir(src_dir):
                    child_path = os.path.join(src_dir, child)
                    log.trace.debug('checking: "%s"' % child_path)
                    if os.path.isdir(child_path):
                        repo_name = "images/" + child
                        self._check_images(child_path, repo_name)
                        for grandchild in os.listdir(child_path):
                            grandchild_path = os.path.join(child_path,\
                             grandchild)
                            log.trace.debug('checking: "%s"' % \
                             grandchild_path)
                            if os.path.isdir(grandchild_path):
                                subrepo_name = "images/" + child + "/" +\
                                 grandchild
                                self._check_images(grandchild_path,\
                                 subrepo_name)
                    else:
                        self._add_error(
                            'Source path "%s" exists but '
                                'is not a directory.' % child_path)
            else:
                self._add_error(
                    'Source path "%s" exists but is not a directory.' % \
                    src_dir)

        # Checksum evaluation and copy to repo

        for imagefile in self._images.iterkeys():
            self._add_action(self.VERB_VERIFY_CHECKSUM, {
                "image_filename": os.path.basename(imagefile),
                "directory": os.path.dirname(imagefile)
            })

        # One RSYNC action for all of the "/images/" tree
        if os.path.exists(src_dir):
            self._add_action(self.VERB_RSYNC_IMAGES, {
                 "source": self._path,
            })

        for imagefile, dst in self._imageswithoutmd5.iteritems():
            self._add_action(self.VERB_GENERATE_CHECKSUM, {
                "image_filepath": imagefile,
                "destination": dst,
            })

        for imagefile, dst in self._images.iteritems():
            self._add_action(self.VERB_VERIFY_CHECKSUM, {
                "image_filename": os.path.basename(imagefile),
                "directory": dst
            })

        for imagefile, dst in self._imageswithoutmd5.iteritems():
            self._add_action(self.VERB_VERIFY_CHECKSUM, {
                "image_filename": os.path.basename(imagefile),
                "directory": dst
            })

    @staticmethod
    def _get_ms_os_major_version():
        # return OS major version number
        _, version, _ = platform.linux_distribution()
        return version[0]

    def _validate_yum_repos(self):
        repo_rhel_suffix = "_rhel" + self._get_ms_os_major_version()
        # Check for new RPMs for LITP and 3PP repos
        self._check_repo(self._iso_path("litp/plugins"), "litp")
        self._check_repo(self._iso_path("litp/3pp"), "3pp" + repo_rhel_suffix)

        PLUGIN_ROOT = 'litp/plugins'

        # Check for application-specific LITP plugins
        src_dir = self._iso_path(PLUGIN_ROOT)

        repo_name = "litp_plugins"
        if os.path.exists(src_dir):
            log.trace.debug('Looking at : "%s"' % src_dir)
            if os.path.isdir(src_dir):
                for child in os.listdir(src_dir):
                    child_path = os.path.join(src_dir, child)
                    log.trace.debug('checking: "%s"' % child_path)
                    if os.path.isdir(child_path):
                        self._check_repo(child_path, repo_name)

        REPO_ROOT = 'repos'

        # Check for application-specific repos
        src_dir = self._iso_path(REPO_ROOT)

        if os.path.exists(src_dir):
            log.trace.debug('Looking at : "%s"' % src_dir)
            if os.path.isdir(src_dir):
                for child in os.listdir(src_dir):
                    child_path = os.path.join(src_dir, child)
                    log.trace.debug('checking: "%s"' % child_path)
                    if os.path.isdir(child_path):
                        repo_name = child + repo_rhel_suffix
                        self._check_repo(child_path, repo_name)
                        for grandchild in os.listdir(child_path):
                            grandchild_path = os.path.join(child_path,
                                                           grandchild)
                            log.trace.debug('checking: "%s"' % grandchild_path)
                            if os.path.isdir(grandchild_path):
                                repo_name = child + "_" + grandchild +\
                                            repo_rhel_suffix

                                self._check_repo(grandchild_path, repo_name)
            else:
                self._add_error(
                    'Source path "%s" exists but is not a directory.' % \
                    src_dir)

        # Add action to clean yum cache if any repos were updated
        if self.VERB_CREATE_REPO in [a['verb'] for a in self._actions]:
            self._add_action(self.VERB_CLEAN_YUM_CACHE, {})

    def _validate_yum_upgrade(self):
        self._add_action(self.VERB_INSTALL_RPMS, {})

    def validate(self):
        """
        Check the ISO layout, returning errors if any are found.

        Also compiles a list of actions which must be performed to
        import this ISO.  Action list can be retrieved later
        by calling get_actions().
        """
        self._valid = False
        self._errors = []
        self._actions = []

        if not os.path.isabs(self._path):
            return self._fatal_error(
                'Source path "%s" must be an absolute path.' % \
                self._path)

        if os.path.exists(self._path):
            if not os.path.isdir(self._path):
                return self._fatal_error(
                    'Source path "%s" exists but is not a directory.' % \
                    self._path)
        else:
            return self._fatal_error(
                'Source directory "%s" does not exist.' % \
                self._path)

        self._validate_images()
        self._add_action(self.VERB_DISABLE_PUPPET, {})
        self._validate_yum_repos()
        if len(self._actions) == 1 and not self._errors:
            return self._fatal_error('No LITP compliant ISO to import')
        self._validate_yum_upgrade()
        self._add_action(self.VERB_ENABLE_PUPPET, {})
        if not self._errors:
            self._valid = True
        return self._errors

    def get_actions(self):
        if not self._valid:
            raise InvalidIsoException("Invalid ISO!")
        return self._actions


class IsoImporter(EventEmitter):
    '''
    Class to be instantiated inside of the import_iso script.
    Contain the actions to be run by the forked grand child process.
    It's instantiated with the parameters passed to the import_iso script.
    Contains methods per each action available in the parser, plus a run method
    that will execute the actions stored in the parser in order, by calling the
    aforementioned action methods.
    '''
    RC_SUCCESS = 0
    RC_ERROR = 1

    class DummyCallbackAPI(object):
        # This is needed to let us use NoStandardErrorRpcCommandProcessor
        def rpc_command(self, nodes, agent, action,
                        action_kwargs=None, timeout=None, retries=0):
            return run_rpc_command(
                      nodes, agent, action, action_kwargs, timeout, retries)

    def __init__(self, path, ms, nodes, callback_api=None):
        super(IsoImporter, self).__init__()
        self._path = path
        self._ms = ms
        self._nodes = nodes
        if callback_api is None:
            callback_api = self.DummyCallbackAPI()
        self._callback_api = callback_api

        log.trace.debug('path: "%s", ms: "%s", nodes: "%s"' %  \
                        (self._path, self._ms, self._nodes))

        self._command_processor = NoStandardErrorRpcCommandProcessor()
        # Handlers have to be set as they got disabled in this process
        litp.metrics.set_handlers()
        apply_metrics(self)

    def _verify_checksum(self, image_filename, directory):
        """ Run createrepo by mco agent"""

        log.trace.info('ISO Importer is running verify_checksums.')

        action_kwargs = {
            'image_filename': image_filename,
            'directory': directory
        }

        try:
            out, errors = self._command_processor.\
                            execute_rpc_and_process_result(
                            self._callback_api,
                            [self._ms],
                            'importiso',
                            'verify_checksum',
                            action_kwargs,
                            timeout=1000
            )
        except RpcExecutionException as e:
            raise Exception(e)
        if errors:
            return reduce_errs(errors)
        else:
            checksum = ()
            for key, value in out.iteritems():
                checksum = (key, value)
            return checksum

    def _generate_checksum(self, image_filepath, destination):
        """ Run createrepo by mco agent"""

        log.trace.info('ISO Importer is running generate_checksums.')

        action_kwargs = {
            'image_filepath': image_filepath,
            'destination_path': destination
        }

        try:
            out, errors = self._command_processor.\
                            execute_rpc_and_process_result(
                            self._callback_api,
                            [self._ms],
                            'importiso',
                            'generate_checksum',
                            action_kwargs,
                            timeout=1000
            )
        except RpcExecutionException as e:
            raise Exception(e)
        if errors:
            return reduce_errs(errors)

    def _create_repo(self, directory):
        """ Run createrepo by mco agent"""

        log.trace.info('ISO Importer is running createrepo.')
        self.emit('_create_repo', directory, IsoParser.REPO_ROOT + '/')

        action_kwargs = {
            'destination_path': directory,
        }

        try:
            out, errors = self._command_processor.\
                            execute_rpc_and_process_result(
                            self._callback_api,
                            [self._ms],
                            'packagesimport',
                            'create_repo',
                            action_kwargs,
                            timeout=1000
            )
        except RpcExecutionException as e:
            raise Exception(e)
        if errors:
            return reduce_errs(errors)

    def _clean_yum_cache(self):
        """ Clean yum cache by mco agent"""

        log.trace.info('ISO Importer is cleaning yum metadata.')

        all_nodes = list(self._nodes)
        all_nodes.append(self._ms)

        try:
            out, errors = self._command_processor.\
                            execute_rpc_and_process_result(
                            self._callback_api,
                            all_nodes,
                            'packagesimport',
                            'clean_yum_cache',
            )
        except RpcExecutionException as e:
            raise Exception(e)
        if errors:
            return reduce_errs(errors)

    def _rsync_rpms(self, source, destination):
        """ Run rsync by mco agent"""

        log.trace.info('ISO Importer is running rsync rpms.')
        log.trace.debug('source: "%s"' % source)
        log.trace.debug('destination: "%s"' % destination)
        self.emit('_rsync_rpms', destination, IsoParser.REPO_ROOT + '/')

        # For rsync, source directory path needs to end with "/"
        if source[-1] != '/':
            source += '/'

        action_kwargs = {
            'source_path': source,
            'destination_path': destination,
            'import_appstream': str(False)
        }

        try:
            out, errors = self._command_processor.\
                            execute_rpc_and_process_result(
                            self._callback_api,
                            [self._ms],
                            'packagesimport',
                            'rsync_packages',
                            action_kwargs,
                            timeout=1000
            )
        except RpcExecutionException as e:
            raise Exception(e)
        if errors:
            return reduce_errs(errors)

    def _rsync_images(self, source):
        """ Run rsync by mco agent"""

        log.trace.info('ISO Importer is running rsync images.')
        log.trace.debug('source: "%s"' % source)

        action_kwargs = {
            'source_path': source,
        }

        try:
            out, errors = self._command_processor.\
                            execute_rpc_and_process_result(
                            self._callback_api,
                            [self._ms],
                            'importiso',
                            'rsync_images',
                            action_kwargs,
                            timeout=1000
            )
        except RpcExecutionException as e:
            raise Exception(e)
        if errors:
            return reduce_errs(errors)

    def _result_to_error(self, result, ignore=None):
        errors = []
        for node, res in result.items():
            if res["errors"]:
                if not ignore or (ignore and ignore not in res["errors"]):
                    errors.append("{0}: {1}".format(node, res["errors"]))
                elif ignore and ignore in res["errors"]:
                    log.trace.info("Ignoring message: {0}".format(
                        res["errors"]))

        return errors

    def _enable_puppet(self):
        log.trace.debug('entering _enable_puppet()')
        ignore = "Already enabled"
        puppet_errors = []
        try:
            log.trace.debug('ISO Importer is updating litp_config_version.')
            new_catalog_version = PuppetCatalogRunProcessor().\
                            update_config_version()
            log.trace.info('ISO Importer is enabling Puppet on the MS')
            ms_st = time.time()
            res = PuppetMcoProcessor().enable_puppet([self._ms])
            ms_et = time.time()
            puppet_errors.extend(self._result_to_error(res, ignore=ignore))
            if not puppet_errors:
                log.trace.info('ISO Importer is triggering Puppet on the MS '
                    'to apply new changes and will wait for the run '
                    'to finish')
                PuppetCatalogRunProcessor().trigger_and_wait(
                        new_catalog_version, [self._ms])
                ms_et = time.time()
                log.trace.info('ISO Importer is enabling Puppet on '
                    'the peer nodes')
                mns_st = time.time()
                res = PuppetMcoProcessor().enable_puppet(self._nodes)
                mns_et = time.time()
                puppet_errors.extend(self._result_to_error(res, ignore=ignore))
                if not puppet_errors:
                    log.trace.info('ISO Importer is triggering Puppet on '
                        'the peer nodes '
                        'to apply new changes and will wait for the run '
                        'to finish')
                    PuppetCatalogRunProcessor().trigger_and_wait(
                                                    new_catalog_version,
                                                    self._nodes)
                    mns_et = time.time()
        except RpcExecutionException as e:
            puppet_errors.append(str(e))

        try:
            ms_tt_metric = {'TimeTaken': '{0:.3f}'.format(ms_et - ms_st)}
            apply_metrics.run_puppet_on_ms_metric.log(ms_tt_metric)
            mns_tt_metric = {'TimeTaken': '{0:.3f}'.format(mns_et - mns_st)}
            apply_metrics.run_puppet_on_mns_metric.log(mns_tt_metric)
        except NameError:
            pass

        return puppet_errors

    def _disable_puppet(self):
        log.trace.info('ISO Importer is disabling Puppet.')
        ignore = "Already disabled"
        try:
            res = PuppetMcoProcessor().disable_puppet([self._ms] + self._nodes)
        except RpcExecutionException as e:
            raise Exception(e)
        if not self._result_to_error(res, ignore=ignore):
            PuppetExecutionProcessor().wait([self._ms] + self._nodes)
        return self._result_to_error(res, ignore=ignore)

    def run(self):
        '''
        This method will set up the state file prior to run the actions, then
        will execute them in order and will retrieve errors that may appear.
        After actions are run, depending if there were errors in any of them,
        the state file will store the success or not of the operation.
        '''
        try:
            StateFile.write_state(StateFile.STATE_RUNNING)
            rc = self._run_worker()
            if rc == IsoImporter.RC_SUCCESS:
                StateFile.write_state(StateFile.STATE_DONE)
            else:
                StateFile.write_state(StateFile.STATE_FAILED)
            return rc
        except:
            # unfortunately we have no access to the model manager here, since
            # this code runs inside the forked process.
            # this means that if this second write_state fails we
            # have no way to communicate a failure until we have
            # some sort of DB we can write to.
            StateFile.write_state(StateFile.STATE_FAILED)
            raise

    def _run_worker(self):

        parser = IsoParser(self._path, RepoPathChecker())
        errors = parser.validate()

        if errors:
            log.trace.error('ISO Importer failure: %s' % errors)
            return self.RC_ERROR

        log.trace.debug('ISO Importer actions {{{')
        for action in parser.get_actions():
            log.trace.debug('  %s' % action)
        log.trace.debug('}}}')

        yum_import = YumImport()

        verb_handlers = {
            IsoParser.VERB_VERIFY_CHECKSUM: self._verify_checksum,
            IsoParser.VERB_GENERATE_CHECKSUM: self._generate_checksum,
            IsoParser.VERB_RSYNC_RPMS: self._rsync_rpms,
            IsoParser.VERB_RSYNC_IMAGES: self._rsync_images,
            IsoParser.VERB_CREATE_REPO: self._create_repo,
            IsoParser.VERB_CLEAN_YUM_CACHE: self._clean_yum_cache,
            IsoParser.VERB_INSTALL_RPMS: yum_import.import_packages,
            IsoParser.VERB_ENABLE_PUPPET: self._enable_puppet,
            IsoParser.VERB_DISABLE_PUPPET: self._disable_puppet
        }

        for action in parser.get_actions():
            try:
                handler = verb_handlers[action['verb']]
            except KeyError:
                log.trace.error('ISO Importer: no handler for verb: %s' %\
                    action['verb'])
                log.trace.debug('ISO Importer run method returned %d'
                    % self.RC_ERROR)
                return self.RC_ERROR
            log.trace.debug(
                '========== Running handler for %s ==========' % \
                action['verb'])
            errors = handler(**action['args'])
            if errors:
                log.trace.error('ISO Importer failure: %s' % errors)
                log.trace.debug('ISO Importer run method returned %d'
                    % self.RC_ERROR)
                return self.RC_ERROR

        log.trace.debug('ISO Importer run method returned %d' %
                        self.RC_SUCCESS)
        return self.RC_SUCCESS


def run_detached_child(path, args):
    # A variation on the Unix double-fork magic; see Stevens's book
    # "Advanced Programming in the UNIX Environment" (Addison-Wesley)
    # for details

    # Parameters are exactly as for os.execv()

    # The basic idea is that we spawn a child process which in turn
    # spawns another child (the "grandchild").  The child then exits,
    # which leaves the grandchild as an orphan, so it gets "reparented"
    # to the "init" process (pid 1).  We then use the grandchild to exec()
    # the desired program.  The whole point is that since "init" is now
    # the parent of the new process, we don't have to worry about reaping
    # it when it's dead.  It's the job of "init" to manage it from now on.

    try:
        pid = os.fork()
        if pid > 0:
            # We are in the parent process.  Just wait for the first
            # child to exit (so that it doesn't become a zombie).
            log.trace.debug('Forked first child, with pid: %d' % pid)
            _, status = os.waitpid(pid, 0)
            log.trace.debug(' first child exited with status: %d' % status)
            return

        # We're now the first child - now spawn another
        try:
            pid = os.fork()
            if pid > 0:
                log.trace.debug('Forked grandchild, with pid: %d' % pid)
                # Don't hang around - we exit so that the second child
                # will be inherited by init(1).
                os._exit(0)
        except OSError as e:
            print >>sys.stderr, "fork #2 failed: %d (%s)" % (
                e.errno, e.strerror)
            raise ForkError("Fork #2 in import_iso failed")
    except OSError as e:
        print >>sys.stderr, "fork #1 failed: %d (%s)" % (
            e.errno, e.strerror)
        raise ForkError("Fork #1 in import_iso failed")

    # If we get here, we're in the second child (grandchild) process.
    # Decouple from parent environment
    os.chdir("/")
    os.setsid()
    os.umask(UMASK)

    log.trace.debug('Executing target process - path: "%s" args: %s' % \
                    (path, args))

    try:
        os.execv(path, args)
    except OSError as e:
        log.trace.exception(e)
        print >>sys.stderr, "exec failed: %d (%s)" % (
            e.errno, e.strerror)
        StateFile.write_state(StateFile.STATE_FAILED)
        sys.exit(1)


class ISOImport(object):
    """ Import packages and images from an ISO. """

    def __init__(self, source_path, model_manager):
        self.source_path = source_path
        self.model_manager = model_manager

    def _get_ms_node_name(self):
        """ Get ms node hostname """
        return [item for item in self.model_manager.get_all_nodes()
                    if item._extends("ms")][0].hostname

    def _get_installed_node_names(self):
        """ Get hostnames of all nodes not in 'Initial' state"""
        return [node.hostname for node in self.model_manager.get_all_nodes()
                if node.get_state() != ModelItem.Initial]

    def run_import(self):
        """ Run ISO import """
        parser = IsoParser(self.source_path,
                           RepoPathChecker(self.model_manager))
        errors = parser.validate()
        if errors:
            log.trace.error('Import-iso failure: %s' % errors)
            return [ValidationError(error_message=error) for error in errors]

        enter_maintenance_mode(self.model_manager)

        log.trace.info('Starting ISO import process with source: ' + \
                         str(self.source_path))

        ms = self._get_ms_node_name()
        managed_nodes = [n for n in self._get_installed_node_names()
                         if n != ms]
        command_args = [
            '/opt/ericsson/nms/litp/bin/iso_importer.py',
            '-p', self.source_path,
            '-m', ms,
        ]

        if log.trace.isEnabledFor(logging.DEBUG):
            command_args.append('-d')

        if managed_nodes:
            command_args.append('-n')
            command_args.extend(managed_nodes)

        log.trace.debug('Import-iso is launching process: %s' %\
            str(command_args))
        try:
            StateFile.write_state(StateFile.STATE_STARTING)
            run_detached_child(
                '/opt/ericsson/nms/litp/bin/iso_importer.py',
                command_args)
        except ForkError as e:
            return [ValidationError(error_type=INTERNAL_SERVER_ERROR,
                                    error_message=str(e))]
        except IOError:
            # could not open state file
            msg = 'Could not open file to track import_iso status'
            return [ValidationError(error_type=INTERNAL_SERVER_ERROR,
                                    error_message=msg)]
