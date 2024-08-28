from subprocess import Popen, PIPE
from collections import defaultdict
from time import sleep
import re
import time
import simplejson
import socket
import os
import pwd
import cherrypy
import subprocess

from litp.core.config import config
from litp.core.constants import BASE_RPC_NO_ANSWER
from litp.core.litp_logging import LitpLogger
from litp.core.exceptions import RpcExecutionException,\
    McoRunError, ServiceKilledException, McoTimeoutException

from grp import getgrnam
from pwd import getpwnam

log = LitpLogger()


def is_puppet_enable_disable(result):
    if "data" not in result or "status" not in result["data"]:
        return False
    status = result["data"]["status"]
    if (isinstance(status, basestring) and
            ("Could not disable Puppet: Already disabled" in status or
             "Could not enable Puppet: Already enabled" in status)):
        return True
    return False


def is_puppet_already_applying(result):
    # LITPCDS-12468: Already applying from enable action
    if ("Puppet is currently applying a catalog, cannot run now" in
            result['errors']):
        return True
    return False


def has_errors(mco_result):
    if not mco_result or not isinstance(mco_result, dict):
        return False
    for hostname in mco_result:
        # Even though there are errors, ignore them if it's an enable action
        # and puppet is already enabled or it's a disable action and puppet is
        # already disabled.
        if is_puppet_enable_disable(mco_result[hostname]):
            continue
        if is_puppet_already_applying(mco_result[hostname]):
            continue
        if mco_result[hostname]["errors"]:
            return True
    return False


def run_rpc_command(nodes, agent, action,
                    action_kwargs=None, timeout=None, retries=0):
    '''
    Returns a dictionary comprising the output of an MCo action performed on a
    set of hosts.
    :return: A dictionary with hostnames (as str objects) as keys and
        dictionaries summarising the output of the action on that host as
        values.
    :rtype: dict
    '''

    if timeout is None:
        timeout = 60
    missed_nodes = nodes
    all_results = {}
    for i in xrange(retries + 1):
        args = _create_rpc_args(
            missed_nodes, agent, action, action_kwargs, timeout
        )
        stdout, stderr = _run_process(args)
        res, missed_nodes = _process_rpc_command(stdout, stderr, missed_nodes)
        all_results.update(res)
        if not missed_nodes:
            break
        if retries:
            # avoid a log message saying retry 0 of 0
            log.trace.info("rpc command with args {0} missed response from {1}"
                           ". Retry {2} of {3}".format(
                args, missed_nodes, i, retries)
            )
    return all_results


def clean_puppet_cache():
    stdout, _ = _run_process(['/usr/bin/puppet', 'config', 'print',
                              'server', '--confdir=/etc/puppet',
                              '--log_level=notice'])
    the_server = stdout.strip()   # pylint: disable=E1103
    log.trace.info("clean_puppet_cache: puppet server: %s" % the_server)
    if the_server:
        log.trace.info("clean_puppet_cache: cleaning puppetcache")
        run_rpc_command([the_server], 'puppetcache', 'clean')
    else:
        log.trace.info("clean_puppet_cache: puppet server not known, "
                       "cannot clean puppetcache")


def run_rpc_application_with_output(nodes, app_args):
    all_results = {}
    app_args.insert(0, 'mco')
    for node in nodes:
        app_args.extend(['-I', node])
    app_args.append('--json')
    stdout, stderr = _run_process(app_args)
    res, _ = _process_rpc_command(stdout, stderr, nodes)
    all_results.update(res)
    return all_results


def run_rpc_application(nodes, app_args):
    app_args.insert(0, 'mco')
    for node in nodes:
        app_args.extend(['-I', node])
    app_args.append('--json')
    return _run_process(app_args, get_retcode=True)[0]


def _create_rpc_args(nodes, agent, action, action_kwargs, timeout):
    args = ['mco', 'rpc', '--json', '--timeout=%s' % timeout]
    for node in nodes:
        args.extend(['-I', node])
    args.extend([agent, action])
    if action_kwargs:
        args.extend(['='.join(i) for i in action_kwargs.iteritems()])
    return args


def _run_process(command_args, get_retcode=False):
    # mcollective needs the HOME env var set or it might fail
    home_dir = pwd.getpwuid(os.getuid())[5]
    env = os.environ.copy()
    env['HOME'] = home_dir
    log.trace.debug("executing command: %s", command_args)
    p = Popen(command_args, stdin=None, stdout=PIPE, stderr=PIPE, env=env)
    stdout, stderr = p.communicate()
    if get_retcode:
        return p.returncode, stderr
    return stdout, stderr


def _process_rpc_command(stdout, stderr, nodes):
    if stderr:
        log.trace.debug("command stderr: %s", stderr)
    log.trace.debug("command stdout: %s", stdout)
    results = {}
    try:
        # We need to ensure all basestr instances in output are unicode
        # instances. We achieve this by decoding stdout (a str instance) to
        # unicode before passing it to simplejson.loads().
        output = simplejson.loads(stdout.decode('UTF8'))
    except ValueError:
        # create understandable output with the error msg
        output = [{'sender': node,
                   'data': {},
                   'statuscode': 1,
                   'statusmsg': stderr} for node in nodes]
    for node_result in iter(output):
        # Hostnames are known to contain only ASCII characters and have already
        # been validated by the LITP model - we can safely represent them as
        # str objects.
        results[str(node_result['sender'])] = {
            # The value associated to the 'data' key is a dict in which all
            # strings are unicode objects.
            'data': node_result['data'],
            # The value associated to the 'errors' key is always a unicode
            # object
            'errors': _find_errors(node_result)
        }
    # if there is no output for a node we assume something went wrong,
    # but take into account that the action might have been done and for some
    # reason mcollective failed to gather the result
    missed_nodes = set(nodes) - set(results.iterkeys())
    for missed_node in missed_nodes:
        results[str(missed_node)] = {
            'data': {},
            'errors': u"{0} {1}".format(BASE_RPC_NO_ANSWER, missed_node)
        }
    return results, missed_nodes


def _find_errors(node_result):
    # About statuscode in mcollective:
    # Status Code    Description
    # 0    OK
    # 1    OK, failed. All the data parsed ok, we have a action matching the
    # request but the requested action could not be completed.
    # 2    Unknown action
    # 3    Missing data
    # 4    Invalid data
    # 5    Other error
    if node_result['statuscode'] != 0:
        return u"{0}: {1}".format(node_result['sender'],
                                 node_result['statusmsg'])
    # hopefully, the common case
    return u""


def reduce_errs(errors):
    # gets the errors dictionary and transforms it into a list of strings,
    # rather than the list of list of errors that you would get with .values()
    return reduce(lambda l1, l2: l1 + l2, errors.values(), [])


class BaseRpcCommandProcessor(object):
    # DEPRECATED AFTER SP14 AND KEPT ONLY NOT TO BREAK BACKWARDS COMPATIBILITY
    # please use RpcCommandProcessorBase instead
    def execute_rpc_and_process_result(self,
                                       api,
                                       nodes,
                                       agent,
                                       action,
                                       action_kwargs=None,
                                       timeout=None,
                                       retries=0,
                                       extra_args=()):
        try:
            result = api.rpc_command(
                nodes, agent, action,
                action_kwargs, timeout, retries
            )
        except Exception as e:
            raise RpcExecutionException(e)
        errs, out = [], {}
        for node in nodes:
            self._look_for_errors_in_node(node, result[node], errs, extra_args)
            if hasattr(self, 'get_output'):
                out[node] = self._get_output(node, result[node])
        return out, errs

    def _look_for_errors_in_node(self, node, agent_result, errors, args):
        if agent_result.get('errors'):
            errors.append(agent_result.get('errors'))
        elif self._errors_in_agent(node, agent_result, *args):
            errors.append(self._errors_in_agent(node, agent_result, *args))
        return errors

    def _errors_in_agent(self, node, agent_result):
        if agent_result.get('data', {}).get('status'):
            return "{0} failed with message: {1}".format(
                node, agent_result.get('data', {}).get('err')
            )
        return ""

    def _get_output(self, node, agent_result):
        pass


def sleep_if_not_killed(timeout, killed=False, sleep_method=None):
    while timeout > 0 and not killed:
        if sleep_method:
            sleep_method(0.5)
        else:
            sleep(0.5)
        timeout -= 0.5
    if killed:
        raise ServiceKilledException(
                "Service was killed while waiting for puppet.")


class RpcCommandProcessorOutput(BaseRpcCommandProcessor):
    # DEPRECATED AFTER SP14 AND KEPT ONLY NOT TO BREAK BACKWARDS COMPATIBILITY
    # please use RpcCommandOutputProcessor instead
    get_output = True

    def _get_output(self, node, agent_result):
        return agent_result.get('data', {}).get('out')


class RpcCommandProcessorBase(object):
    def execute_rpc_and_process_result(self,
                                       api,
                                       nodes,
                                       agent,
                                       action,
                                       action_kwargs=None,
                                       timeout=None,
                                       retries=0,
                                       extra_args=()):
        try:
            result = api.rpc_command(
                nodes, agent, action,
                action_kwargs, timeout, retries
            )
        except Exception as e:
            raise RpcExecutionException(e)
        return self._process_result(result, nodes, extra_args)

    def _process_result(self, result, nodes, extra_args):
        errs, out = defaultdict(list), {}
        for node in nodes:
            self._look_for_errors_in_node(node, result[node], errs, extra_args)
            if hasattr(self, 'get_output'):
                out[node] = self._get_output(node, result[node])
        return out, errs

    def _look_for_errors_in_node(self, node, agent_result, errors, args):
        if agent_result.get('errors'):
            errors[node].append(agent_result.get('errors'))
        elif self._errors_in_agent(node, agent_result, *args):
            errors[node].append(
                self._errors_in_agent(node, agent_result, *args)
            )
        return errors

    def _errors_in_agent(self, node, agent_result):
        status = agent_result.get('data', {}).get('status')
        if status:
            err = agent_result.get('data', {}).get('err')
            if err:
                return "{0} failed with message: {1}".format(node, err)
            else:
                return \
                    "{0} failed without any error message but with status {1}"\
                        .format(node, status)
        return ""

    def _get_output(self, node, agent_result):
        pass


class RpcCommandOutputProcessor(RpcCommandProcessorBase):
    get_output = True

    def _get_output(self, node, agent_result):
        return agent_result.get('data', {}).get('out', '')


class NoStandardErrorRpcCommandProcessor(RpcCommandProcessorBase):
    """A command processor that treats the appearance of anything on
       standard error as failure."""

    def _errors_in_agent(self, node, agent_result):
        error = super(NoStandardErrorRpcCommandProcessor, self). \
            _errors_in_agent(node, agent_result)
        if not error:
            status = agent_result.get('data', {}).get('status')
            stderr_text = agent_result.get('data', {}).get('err')
            if stderr_text:
                error = "{0} produced error message: {1}". \
                    format(node, stderr_text)
        return error


class RpcCommandOutputNoStderrProcessor(NoStandardErrorRpcCommandProcessor):
    """Combines stderr-checking of NoStandardErrorRpcCommandProcessor
       with stdout-processing of RpcCommandOutputProcessor."""
    get_output = True

    def _get_output(self, node, agent_result):
        return agent_result.get('data', {}).get('out', '')


class LockFilePuppetProcessor(RpcCommandOutputProcessor):
    def _get_output(self, node, agent_result):
        return agent_result.get('data', {}).get('is_running', True)


class PuppetUtilsProcessor(RpcCommandOutputProcessor):
    def _refresh_node_stats_lockfile(self, nodes):
        # Retrieves whether a catalog run is ongoing for each node, based on
        # puppet's lockfile. We need to do this due to a bug in the mcollective
        # agent, which will say that there is no Puppet catalog being applied
        # when Puppet is disabled, even if there is a catalog running.

        try:
            result = run_rpc_command(nodes, 'puppetlock', 'is_running',
                                     timeout=20)
        except Exception as e:
            raise RpcExecutionException(e)

        out, errs = LockFilePuppetProcessor()._process_result(result,
                                                              nodes,
                                                              extra_args=())
        if errs:
            raise McoRunError()

        return out


class PuppetCatalogRunProcessor(PuppetUtilsProcessor):
    DEFAULT_GROUP = "puppet"
    CELERY_USER = "celery"
    PUPPET_CONCURRENCY = 10

    def __init__(self, max_iterations=3000, wait_interval=5):
        # hostname list of the nodes which we want to trigger and wait
        self.nodes = []
        self.agent_key = 'config_version'
        self.max_iterations = max_iterations
        self.wait_interval = wait_interval
        self.litp_root = cherrypy.config.get("litp_root",
            "/opt/ericsson/nms/litp")

    def config_version_file(self):
        return os.path.join(
            self.litp_root,
            "etc/puppet/litp_config_version")

    def _write_file(self, filepath, contents):
        log.trace.debug("Changing litp_config_version file with the Puppet"
                       "version that will be applied: {0}".format(contents))
        dirpath = os.path.dirname(os.path.abspath(filepath))
        if not self._exists(dirpath):
            self._makedirs(dirpath)
        pp_file = self._open_file(filepath)
        self._fchmod(pp_file, 0644)
        pp_file.write(contents)
        pp_file.flush()
        os.fsync(pp_file.fileno())
        pp_file.close()

    def _exists(self, filename):
        return os.path.exists(filename)

    def _makedirs(self, dirpath):
        os.makedirs(dirpath)

    def _open_file(self, filename, mode="w"):
        return open(filename, mode)

    def _fchmod(self, file_instance, mode):
        os.fchmod(file_instance.fileno(), mode)

    def _chown(self, dir_path):
        try:
            os.chown(dir_path,
                     getpwnam(PuppetCatalogRunProcessor.CELERY_USER).pw_uid,
                     getgrnam(PuppetCatalogRunProcessor.DEFAULT_GROUP).gr_gid)
        except KeyError as e:
            log.trace.warning("Could not set file ownership of dir %s. %s" %
                              (dir_path, str(e)))

    def manifest_dir(self, manifest_dir="plugins"):
        return os.path.join(
            self.litp_root, "etc/puppet/manifests/", manifest_dir)

    def _touch_manifest_dir(self, times=None):
        log.trace.debug('Touching manifest_dir to trigger catalog compilation')
        mdir = self.manifest_dir()
        self._chown(mdir)
        os.utime(mdir, times)

    def _errors_in_agent(self, node, agent_result):
        # no errors specific to the agent, only the generic mco ones
        return ""

    def _get_output(self, node, agent_result):
        return agent_result.get('data', {})

    def update_config_version(self):
        """Atomically increment config_version - Function in use by ENMinst."""
        from litp.core.nextgen.puppet_manager import PuppetManager
        return PuppetManager(None).write_new_config_version()

    @staticmethod
    def _disable_puppet(hostnames, enable_exception=False):
        try:
            res = run_rpc_command(hostnames, "puppet", "disable")
            if has_errors(res):
                log.trace.error("Error occurred "
                                "disabling Puppet.")

        except Exception as e:  # pylint: disable=W0703
            log.trace.info("Exception: {0} occurred.".format(e))
            if enable_exception:
                raise RpcExecutionException(e)

    @staticmethod
    def _enable_puppet(hostnames, enable_exception=False):
        try:
            res = run_rpc_command(hostnames, "puppet", "enable")
            if has_errors(res):
                log.trace.error("Error occurred "
                                "enabling Puppet.")
        except Exception as e:  # pylint: disable=W0703
            log.trace.info("Exception: {0} occurred.".format(e))
            if enable_exception:
                raise RpcExecutionException(e)

    @staticmethod
    def _is_plan_running():
        cmd = "litp show -p /plans/plan | grep -q 'state: running'"
        return subprocess.call(cmd, shell=True, stdout=subprocess.PIPE) == 0

    def _get_failed_nodes(self, node_list, untriggered_nodes, applying_nodes):
        """
        Get a list of nodes that have been triggered
        but are no longer applying to add them to the failed list.
        """
        nodes = set(node_list)
        _triggered_nodes = set(nodes - untriggered_nodes)
        log.trace.info("Triggered_nodes: {0}".format(', '.join(
            list(sorted(_triggered_nodes)))))
        failed_nodes = _triggered_nodes - applying_nodes
        if failed_nodes:
            log.trace.info("Failed nodes {0}".format(', '.join(
                list(sorted(failed_nodes)))))
        return failed_nodes

    def _wait_for_nodes_to_apply(self, nodes):
        nodes_remaining = set(nodes)
        log.trace.info("Waiting for triggered nodes to apply.")
        for _ in xrange(self.max_iterations):
            if nodes_remaining:
                try:
                    nodes_applying = self._get_applying_nodes(nodes_remaining)
                    nodes_remaining = nodes_remaining - nodes_applying
                    log.trace.info("Nodes remaining: {0}"
                                   .format(', '.join(sorted(nodes_remaining))))
                    if not nodes_remaining:
                        return
                except (RpcExecutionException, McoRunError):
                    pass

    def _trigger_puppet_with_concurrency(self, untriggered_nodes, all_nodes):
        """With an upper threshold on the level of concurrency,
           trigger Puppet on N of the, as yet untriggered, nodes."""
        log.trace.info("Untriggered nodes: {0}"
                       .format(', '.join(list(sorted(untriggered_nodes)))))
        try:
            applying_nodes = self._get_applying_nodes(all_nodes)
        except (McoRunError, RpcExecutionException) as exception:
            log.trace.error("Exception {0} occurred getting applying nodes"
                            .format(str(exception)))
            return set()

        log.trace.info("Applying nodes: {0}"
                       .format(', '.join(list(sorted(applying_nodes)))))

        num_applying_nodes = len(applying_nodes)

        if PuppetCatalogRunProcessor.PUPPET_CONCURRENCY > num_applying_nodes:
            nodes_to_trigger = set(list(untriggered_nodes - applying_nodes)
                                   [:PuppetCatalogRunProcessor.
                                   PUPPET_CONCURRENCY - num_applying_nodes])
            if nodes_to_trigger:
                log.trace.info("Enabling Puppet on nodes: {0}"
                               .format(', '.join(list(
                                       sorted(nodes_to_trigger)))))
                self._enable_puppet(nodes_to_trigger)
                triggered_nodes = self._trigger_puppet(nodes_to_trigger)
                self._wait_for_nodes_to_apply(triggered_nodes)
                self._disable_puppet(nodes_to_trigger)
                log.trace.info("Disabled nodes {0}"
                               .format(', '.join(sorted(
                                       nodes_to_trigger))))
                return triggered_nodes
        return set()

    def trigger_and_wait(self, version, node_list):
        """Triggers a catalog run in all specified nodes only allowing
           PUPPET_CONCURRENCY nodes to apply concurrently
           and waits for it to finish"""
        def _log_finished():
            log.trace.info(
                "Puppet triggered and completed on nodes {0}".format(
                    re.sub(r'(.*),', r'\1 and', ', '.join(list(
                                                          sorted(node_list)))))
            )

        if self._is_plan_running():
            log.trace.info('LITP plan is running. '
                           'Wait till plan is finished for '
                           'Puppet to be triggered.')
            raise RpcExecutionException("LITP plan is running, "
                                        "wait until plan is finished "
                                        "for Puppet to be trigged.")

        self.nodes = list(node_list)
        untriggered_nodes = set(self.nodes)
        self._touch_manifest_dir()
        all_nodes = self._find_all_nodes()
        log.trace.info("All nodes: {0}"
                       .format(', '.join(list(sorted(all_nodes)))))

        if not all_nodes:
            raise RpcExecutionException("MCO find failed to discover "
                                        "all nodes in the deployment")

        try:
            log.trace.info('Disabling Puppet on all nodes.')
            self._disable_puppet(all_nodes)

            clean_puppet_cache()

            untriggered_nodes = untriggered_nodes - \
                                self._trigger_puppet_with_concurrency(
                                                untriggered_nodes,
                                                all_nodes)

            log.trace.info("Untriggered nodes: {0}".format(untriggered_nodes))

            for _ in xrange(self.max_iterations):
                if not self.nodes:
                    _log_finished()
                    return
                try:
                    applying_nodes = self._get_applying_nodes(self.nodes)
                    log.trace.info("Applying Nodes: {0}".
                                   format(', '.join(sorted(applying_nodes))))
                    untriggered_nodes = untriggered_nodes - \
                                        self._update_refreshed_nodes(version,
                                        self._refresh_node_stats())
                    failed_nodes = self._get_failed_nodes(self.nodes,
                                                          untriggered_nodes,
                                                          applying_nodes)
                    if failed_nodes:
                        untriggered_nodes.update(failed_nodes)
                except (McoRunError, RpcExecutionException):
                    # keep going, we will just not update the data
                    pass
                # avoid calling unnecessarily _wait on the last iteration
                if not self.nodes:
                    _log_finished()
                    return
                self._wait()
                if untriggered_nodes:
                    untriggered_nodes = untriggered_nodes - \
                                        self._trigger_puppet_with_concurrency(
                                            untriggered_nodes,
                                            all_nodes)

            err_msg = "Execution timed out while triggering Puppet on " \
                      "nodes {0} and waiting for it to apply the catalog"\
                .format(re.sub(r'(.*)', r'\ and', ', '
                               .join(list(sorted(self.nodes)))))

            log.trace.info(err_msg)
            raise RpcExecutionException(err_msg)

        finally:
            log.trace.info("Enabling Puppet on all nodes".format(', '.join(
                           list(sorted(all_nodes)))))
            try:
                self._enable_puppet(all_nodes, enable_exception=True)
            except RpcExecutionException:
                log.trace.error("Failed to enable all nodes")
                raise RpcExecutionException

    def _trigger_puppet(self, node_list):
        # runs puppet in a list of nodes and returns
        # a set of the nodes that were triggered
        log.trace.info(
            "Triggering Puppet on nodes {0}".format(', '.join(
                                                    list(sorted(node_list)))))
        out = run_rpc_application_with_output(node_list, ['puppet', 'runonce'])
        for node in out.iterkeys():
            errors = out[node].get('errors')
            if errors:
                log.trace.info("Could not trigger Puppet "
                    "on node {0}: {1}.".format(node, errors))
        return set([n for n in out.iterkeys() if not out[n].get('errors')])

    def _refresh_node_stats(self, source='resource'):
        """ get data regarding the last puppet run """
        try:
            result = run_rpc_command(
                self.nodes, 'rpcutil', 'get_data',
                action_kwargs={'source': source}, timeout=12
            )
        except Exception as e:
            raise RpcExecutionException(e)
        out, errs = self._process_result(result, self.nodes, extra_args=())
        if errs:
            raise McoRunError()
        return out

    def _update_refreshed_nodes(self, version, new_data):
        self._validate_input(new_data)
        completed_nodes = set()
        uncompleted_nodes = [n for n in self.nodes]
        for hostname in uncompleted_nodes:
            log.trace.info("Node: {0}, updated to: {1}, applied: {2}".
                           format(hostname, version,
                                  new_data[hostname][self.agent_key]))
            if new_data[hostname][self.agent_key] >= version:
                log.trace.info("Applied >= updated, no longer waiting for {0}".
                               format(hostname))
                completed_nodes.add(hostname)
                self.nodes.remove(hostname)
        return completed_nodes

    def _validate_input(self, new_data):
        # if something strange comes from mco set it to -1 to avoid problems
        for h in new_data.iterkeys():
            try:
                new_data[h][self.agent_key] = int(
                        new_data[h].get(self.agent_key, -1))
            except ValueError:
                # Convert legacy timestamp config_version to int
                new_data[h][self.agent_key] = 0

    def _wait(self):
        sleep(self.wait_interval)

    def _get_applying_nodes(self, nodes):
        """Returns the set of nodes from nodes that are doing
           a puppet catalog run."""
        new_data = self._refresh_node_stats_lockfile(nodes)
        return set([hostname for hostname in new_data.keys()
                    if new_data[hostname]])

    def _find_all_nodes(self):
        """Run mco find to gather the superset of all hostnames in the
           deployment. That'll be the set of nodes to monitor for Puppet
           applying/idle while triggering new Puppet runs
           :rtype: list
           :return: Puppet node hostnames"""
        stdout, _ = _run_process(['/usr/bin/mco', 'find'])
        if stdout:
            return stdout.split()  # pylint: disable=E1103
        return []


class PuppetExecutionProcessor(PuppetUtilsProcessor):
    def __init__(self, max_iterations=60, wait_interval=5):
        # {hostname: {'state': str, 'lastrun': int}}
        # state can be:
        # prevrun -> Puppet is applying an old catalog
        # nontriggered -> Puppet is idle and waiting to apply the new catalog
        # triggered -> Puppet has been triggered to run the new catalog
        # completed -> Puppet has applied the new catalog
        self.nodes = {}
        self.max_iterations = max_iterations
        self.wait_interval = wait_interval

    def _errors_in_agent(self, node, agent_result):
        # no errors specific to the agent, only the generic mco ones
        return ""

    def _get_output(self, node, agent_result):
        return agent_result.get('data', {})

    def _init_node_data(self, node_list, verify_disabled):
        secs_to_wait = self.max_iterations * self.wait_interval
        timeout = time.time() + secs_to_wait
        while time.time() < timeout:
            try:
                self._init_data(node_list, verify_disabled)
                # get out of the loop once _init_data run successfully once
                return
            except McoRunError:
                # try again after a few secs, might get fixed by itself
                pass
            self._wait()
        raise McoRunError("Could not get Puppet data, "
                          "please check Mcollective logs")

    def trigger_and_wait(self, node_list):
        # triggers a catalog run in all nodes and waits for it to finish
        log.trace.info(
            "Triggering Puppet on nodes {0}".format(', '.join(node_list))
        )
        self._init_node_data(node_list, False)
        for _ in xrange(self.max_iterations):
            pr, nt, _, c = self._get_nodes_by_state()
            if set(c) == set(self.nodes.iterkeys()):
                # all done, stop execution
                log.trace.info(
                    "Puppet triggered and completed on nodes {0}".format(
                        ', '.join(node_list))
                )
                break
            # no need to trigger Puppet if there's no node left to trigger
            if nt:
                self._update_triggered_nodes(self._trigger_puppet(nt))
            try:
                self._update_refreshed_nodes(self._refresh_node_stats())
            except McoRunError:
                # keep going, we will just not update the data
                pass
            self._wait()

    def wait(self, node_list, verify_disabled=True):
        # unlike trigger_and_wait, only waits for all the nodes to stop
        # an ongoing run
        # init_node_data will fill in the lastrun property, state will be
        # overriden by _update_refreshed_nodes_lockfile due to the mco bug
        # mentioned in _refresh_node_stats_lockfile
        self._init_node_data(node_list, verify_disabled)
        self._update_refreshed_nodes_lockfile(
            self._refresh_node_stats_lockfile(self.nodes)
        )

        for _ in xrange(self.max_iterations):
            _, nt, _, c = self._get_nodes_by_state()
            if set(nt + c) == set(self.nodes.iterkeys()):
                # all done, stop execution
                log.trace.info(
                    "Puppet completed run on nodes {0}".format(
                        ', '.join(node_list))
                )
                break
            try:
                self._update_refreshed_nodes(self._refresh_node_stats())
            except McoRunError:
                # keep going, we will just not update the data
                pass
            self._wait()

    def _init_data(self, node_list, verify_disabled=False):
        self.nodes = dict((n, []) for n in node_list)
        new_data = self._refresh_node_stats()
        for hostname in new_data.iterkeys():
            # upon start Puppet can be idle (nontriggered)
            # or applying a catalog (prevrun)
            state = 'nontriggered'
            if new_data[hostname].get('applying', True):
                state = 'prevrun'
            # lastrun provides a timestamp of the last completed puppet run
            self.nodes[hostname] = {
                'lastrun': new_data[hostname].get('lastrun', -1),
                'state': state
            }
            if verify_disabled and new_data[hostname].get('enabled', True):
                raise RpcExecutionException("Puppet not disabled on node {0}".
                                            format(hostname))
            log.trace.debug(
                "Initialised {0} to {1}, last Puppet run in {2}".format(
                    hostname,
                    self.nodes[hostname]['state'],
                    self.nodes[hostname]['lastrun'])
            )

    def _refresh_node_stats(self):
        # get data regarding the last puppet run
        try:
            result = run_rpc_command(
                self.nodes, 'rpcutil', 'get_data',
                action_kwargs={'source': 'puppet'}, timeout=12
            )
        except Exception as e:
            raise RpcExecutionException(e)
        out, errs = self._process_result(result, self.nodes, extra_args=())
        if errs:
            raise McoRunError()
        return out

    def _trigger_puppet(self, node_list):
        # runs puppet in a list of nodes and returns
        # a list of the nodes that were triggered
        clean_puppet_cache()
        out = run_rpc_application_with_output(node_list, ['puppet', 'runonce'])
        return [n for n in out.iterkeys() if not out[n].get('errors')]

    def _get_nodes_by_state(self):
        # returns lists with the nodes in each possible state
        hostnames = self.nodes.keys()
        prevrun, nontriggered, triggered, completed = [], [], [], []
        for n in hostnames:
            state = self.nodes[n]['state']
            if state == 'prevrun':
                prevrun.append(n)
            elif state == 'nontriggered':
                nontriggered.append(n)
            elif state == 'triggered':
                triggered.append(n)
            elif state == 'completed':
                completed.append(n)
        return prevrun, nontriggered, triggered, completed

    def _update_triggered_nodes(self, triggered_list):
        for hostname in triggered_list:
            log.trace.info("{0} triggered a Puppet run".format(hostname))
            self.nodes[hostname]['state'] = 'triggered'

    def _update_refreshed_nodes(self, new_data):
        # also check nodes in nontriggered state because it could happen that
        # in the interval between one check and the next the node gets its
        # catalog applied without litp explicitly triggering it.
        self._validate_input(new_data)
        uncompleted_nodes = [n for n in self.nodes.iterkeys() if
                             self.nodes[n]['state'] not in
                             ('prevrun', 'completed')]
        prevrun_nodes = [n for n in self.nodes.iterkeys() if
                         self.nodes[n]['state'] == 'prevrun']
        for hostname in uncompleted_nodes:
            if self.nodes[hostname]['lastrun'] < new_data[hostname]['lastrun']:
                self.nodes[hostname]['state'] = 'completed'
                log.trace.info("{0} completed a Puppet run: {1} < {2}".
                               format(hostname,
                                      self.nodes[hostname]['lastrun'],
                                      new_data[hostname]['lastrun'])
                               )
        for hostname in prevrun_nodes:
            if self.nodes[hostname]['lastrun'] < new_data[hostname]['lastrun']:
                # a node that was running puppet already when the process begun
                # has now finished that run. We can move it to nontriggered and
                # run puppet in the next iteration
                log.trace.info("{0} completed an old Puppet run: {1} < {2}".
                               format(hostname,
                                      self.nodes[hostname]['lastrun'],
                                      new_data[hostname]['lastrun'])
                               )
                self.nodes[hostname]['state'] = 'nontriggered'
        for hostname in new_data.iterkeys():
            if new_data[hostname]['lastrun'] > \
                    self.nodes[hostname].get('lastrun', 0):
                self.nodes[hostname]['lastrun'] = new_data[hostname]['lastrun']

    def _update_refreshed_nodes_lockfile(self, new_data):
        # if a lockfile is present then there's a puppet catalog being
        # applied in that node. Since Puppet will be already disabled this
        # means that if a lock file exists the puppet run is an old one
        for hostname in new_data.keys():
            if new_data[hostname]:
                self.nodes[hostname]['state'] = 'prevrun'
            else:
                self.nodes[hostname]['state'] = 'nontriggered'

    def _validate_input(self, new_data):
        # if something strange comes from mco set it to -1 to avoid problems
        for h in new_data.iterkeys():
            new_data[h]['lastrun'] = new_data[h].get('lastrun', -1)

    def _wait(self):
        sleep(self.wait_interval)


class PuppetMcoProcessor(RpcCommandOutputProcessor):
    # Maybe we want this in a separate class/config
    MCO_ACTION_CONCURRENCY = 10
    MCO_ACTION_WAIT_BETWEEN_RETRIES = 5  # seconds
    MCO_CLI_TIMEOUT = 10  # seconds

    def __init__(self, sleep_function=sleep_if_not_killed):
        self.PUPPET_RUN_TOTAL_TIMEOUT = config.get('puppet_mco_timeout', 300)
        self.smart_sleep = sleep_function

    def run_puppet(self, hostnames, agent, action, action_kwargs=None,
            deadline=None):
        try:
            if deadline is not None:
                deadline = time.time() + deadline
            return self._run_puppet(
                    hostnames, agent, action, action_kwargs, deadline)
        except McoTimeoutException as e:
            log.trace.error(str(e))
            return e.result

    def _is_litp_killed(self):
        try:
            return cherrypy.config['puppet_manager'].killed
        except KeyError:
            return False  # For external consumers of rpc_commands.py

    def _run_puppet(self, hostnames, agent, action, action_kwargs=None,
            deadline=None):
        result = {}
        if deadline is None:
            deadline = time.time() + self.PUPPET_RUN_TOTAL_TIMEOUT
        hostnames_retry = set()

        def _run_mco_action(hostnames, agent, action, action_kwargs=None):
            '''
            Runs an action from a given MCollective agent on a set of
            hostnames. This function will handle MCollective concurrency and
            process hosts in batches until results have been obtained for the
            full set.
            This function does not implement a retry mechanism, but it does
            update the hostnames_retry list defined in _run_puppet
            This function returns None but updates the result dict defined in
            _run_puppet()
            '''

            all_hostnames = list(hostnames)
            while hostnames:
                if self._is_litp_killed():
                    for hostname in hostnames:
                        result[hostname] = {'errors':
                          'Litp service has been killed'}
                    return result
                hostnames_current_batch, hostnames = \
                    hostnames[:self.MCO_ACTION_CONCURRENCY], \
                    hostnames[self.MCO_ACTION_CONCURRENCY:]
                log.trace.info(
                    "Running action %s from agent %s on hosts: %s",
                    action, agent, ",".join(hostnames_current_batch))
                current_batch_results = self._run_puppet_command(
                    hostnames_current_batch, agent, action, action_kwargs
                )
                result.update(current_batch_results)

            # Inspect results for errors
            hostnames_retry.clear()
            for hostname in all_hostnames:
                if not result[hostname]['errors']:
                    continue
                # Nodes that have the following errors are not to be
                # retried.
                if (
                    (
                        action == "disable" and
                        "Could not disable Puppet: Already disabled" in
                        result[hostname]['errors']
                    ) or (
                        action == "enable" and
                        "Could not enable Puppet: Already enabled" in
                        result[hostname]['errors']
                    )  or (
                        action == "runonce" and
                        "Puppet is currently applying a catalog, "
                            "cannot run now" in result[hostname]['errors']
                    )
                ):
                    continue
                # We have errors for this hostname. Have we got time to retry?
                if time.time() < deadline:
                    log.trace.debug(
                        "Cannot run %s from agent %s on %s: %s, need to retry",
                        action, agent, hostname, result[hostname]['errors'])
                    hostnames_retry.add(hostname)
                else:
                    msg = "Cannot run {0} from agent {1} on {2}: {3}, " \
                        "no more retries".format(
                        action, agent, hostname, result[hostname]['errors']
                    )
                    log.trace.error(msg)
                    raise McoTimeoutException(msg, result)

        _run_mco_action(hostnames, agent, action, action_kwargs)
        # We've queried all hostnames - are there any stragglers and have we
        # got time to try again?
        while hostnames_retry and time.time() < deadline:
            self.smart_sleep(self.MCO_ACTION_WAIT_BETWEEN_RETRIES)
            _run_mco_action(
                sorted(list(hostnames_retry)),
                agent,
                action,
                action_kwargs
            )
        return result

    def _run_puppet_command(self, hostnames, agent, action, action_kwargs,
                            timeout=MCO_CLI_TIMEOUT):
        return run_rpc_command(hostnames, agent, action,
                action_kwargs=action_kwargs, timeout=timeout)

    def _start_stop_puppet_check(self, hostname, wanted_action):
        status_action = {"start": "running",
                         "stop": "stopped"}
        wanted_status = status_action[wanted_action]
        orig_status, res = self._puppet_service_status(hostname)
        changed_state = False
        if orig_status != wanted_status:
            changed_state = True
            action_kwargs = {"service": "puppet"}
            res = self.run_puppet([hostname], "service", wanted_action,
                                            action_kwargs=action_kwargs)
        return (changed_state, res)

    def _start_puppet_check(self, hostname):
        return self._start_stop_puppet_check(hostname, "start")

    def _stop_puppet_check(self, hostname):
        return self._start_stop_puppet_check(hostname, "stop")

    def _puppet_service_status(self, hostname):
        action_kwargs = {"service": "puppet"}
        service_status = self.run_puppet([hostname], "service", "status",
                action_kwargs=action_kwargs)
        try:
            if service_status:
                status = service_status[hostname]['data']['status']
                return (status, service_status)
        except (KeyError, IndexError):
            log.trace.error("Unknown puppet service status: %s",
                                                    str(status))
        return ("unknown", service_status)

    def _runonce_puppet(self, hostnames):
        return self.run_puppet(hostnames, "puppet", "runonce")

    def _get_ms_names(self, ms_hostname):
        resolv_domains = self._get_resolv_domains()
        ms_names = ['%s.%s' % (ms_hostname, h) for h in resolv_domains]
        ms_names.append(socket.getfqdn())
        ms_names.append(ms_hostname)
        ms_names_lower = [n.lower() for n in ms_names]
        return ms_names_lower

    def _get_puppet_certs(self, ms_hostname):
        node_certs = None
        res = self.run_puppet(
            [ms_hostname], "puppetcerts", "list_certs")
        try:
            res = res or {}
            ms_res = res.get(ms_hostname)
            if ms_res:
                node_certs = ms_res["data"]["nodes"]
        except KeyError:
            pass
        return node_certs, res

    def clean_puppet_certs(self, nodes, ms_hostname):
        changed, _ = self._stop_puppet_check(ms_hostname)
        node_certs, res = self._get_puppet_certs(ms_hostname)

        if not node_certs:
            log.trace.info("Couldn't get a list of "
                                "puppet certificates: %s", res)
            if changed:
                self._start_puppet_check(ms_hostname)
            return

        ms_names = set(self._get_ms_names(ms_hostname))
        node_hostnames = set([node.hostname.lower() for node in nodes])

        node_certs_list = node_certs.split(':')
        for cert_hostname in node_certs_list:
            cert_hostname_lower = cert_hostname.lower()
            if (
                cert_hostname_lower in ms_names or
                not cert_hostname_lower in node_hostnames
            ):
                # skip removing cert (case insensitive)
                log.trace.debug(
                    "Excluding cert from removal: %s", cert_hostname)
                continue

            log.audit.info("Removing certificate %s", cert_hostname)
            res = self.run_puppet(
                [ms_hostname], "puppetcerts",
                "clean_cert", {'node': cert_hostname}
                )
            if res and res[ms_hostname]['data']['status'] != 0:
                log.trace.error("Error removing %s: %s", cert_hostname, res)

        if changed:
            self._start_puppet_check(ms_hostname)

    def _get_resolv_domains(self, resolv_file='/etc/resolv.conf'):
        try:
            f = open(resolv_file)
            data = f.readlines()
            r = re.compile(r'^[^#]*(domain|search)\W+(.+)')
            domains = [r.match(i).groups()[1].strip()\
                                    for i in data if r.match(i)]
        except IOError as e:
            log.trace.info("Cannot open /etc/resolv.conf %s", e.strerror())
            return []
        return domains

    def status_puppet(self, hostnames):
        return self.run_puppet(hostnames, "puppet", "status")

    def disable_puppet(self, hostnames):
        return self.run_puppet(hostnames, "puppet", "disable")

    def enable_puppet(self, hostnames, timeout=None):
        return self.run_puppet(hostnames, "puppet", "enable", deadline=timeout)

    def runonce_puppet(self, hostnames):
        return self.run_puppet(hostnames, "puppet", "runonce")

    def puppetlock_clean(self, hostnames):
        return self.run_puppet(hostnames, "puppetlock", "clean")

    def stop_puppet_applying(self, hostnames):
        return self.run_puppet(hostnames, "puppetagentkill",
                               "kill_puppet_agent")

    def clear_puppet_cache(self, hostnames):
        return self.run_puppet(hostnames, "puppetcache", "clean")

    def puppetlock_is_running(self, hostnames):
        try:
            # Update _get_output strategy.
            self._get_output = LockFilePuppetProcessor()._get_output
            return self.run_puppet(hostnames, "puppetlock", "is_running")
        finally:
            # Bring back default _get_output strategy.
            self._get_output = RpcCommandOutputProcessor()._get_output
