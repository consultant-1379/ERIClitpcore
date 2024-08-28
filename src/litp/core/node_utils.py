##############################################################################
# COPYRIGHT Ericsson AB 2013
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################
from litp.core.rpc_commands import run_rpc_command,\
                                   RpcCommandProcessorBase,\
                                   reduce_errs
from litp.core.litp_logging import LitpLogger
from litp.core.exceptions import BadRebootException, CallbackExecutionException
from litp.core.exceptions import PlanStoppedException, RpcExecutionException

import time

log = LitpLogger()
_max_waiting_time_for_node_down = 1800  # 30min
_max_waiting_time_for_node_up = 1800  # 30min
_max_waiting_time_for_puppet_state = 2100  # 35min


class RebootAgent(RpcCommandProcessorBase):
    def _errors_in_agent(self, node, agent_result):
        if agent_result.get('data', {}).get('status') == 0:
            return ""
        elif agent_result.get('data', {}).get('status') == 1:
            return "Not back yet"
        elif agent_result.get('data', {}).get('status') == 2:
            raise BadRebootException(agent_result.get('data', {}).get('err'))
        raise BadRebootException("Unexpected error code: {0}. stderr: {1}".\
                             format(agent_result.get('data', {}).get('status'),
                                    agent_result.get('data', {}).get('err')))


def wait_for_node(callback_api, hostname, stoppable, loose=False):
    _wait_for_callback(
        callback_api,
        ("Waiting for node to come up: %s" % (hostname)),
        stoppable,
        _check_node,
        _max_waiting_time_for_puppet_state,
        hostname,
        loose,
        False
        )
    log.event.info("Node %s has come up.", hostname)


def wait_for_node_puppet_applying_catalog_valid(callback_api, hostname,
                                                stoppable, loose=False):
    _wait_for_callback(
        callback_api,
        ("Waiting for node to come up and puppet state 'applying a catalog' is"
         " acceptable: %s" % (hostname)),
        stoppable,
        _check_node,
        _max_waiting_time_for_puppet_state,
        hostname,
        loose,
        True
        )
    log.event.info("Node %s has come up.", hostname)


def wait_for_node_down(callback_api, hostname, stoppable):
    _wait_for_callback(
        callback_api,
        ("Waiting for node to reboot: %s" % (hostname)),
        stoppable,
        _check_node_down,
        _max_waiting_time_for_node_down,
        hostname
        )
    log.event.info("Node %s is restarting.", hostname)


def reboot_node(callback_api, hostnames):
    bcp = RpcCommandProcessorBase()
    _, errors = bcp.execute_rpc_and_process_result(callback_api,
                                                   hostnames,
                                                   'core',
                                                   'reboot')
    if errors:
        raise RpcExecutionException(','.join(reduce_errs(errors)))


def reboot_node_force(callback_api, hostnames):
    bcp = RpcCommandProcessorBase()
    # the node won't come back after it has been executed, so it is worthless
    # to try look for an error
    _, _ = bcp.execute_rpc_and_process_result(callback_api,
                                              hostnames,
                                              'core',
                                              'reboot_force')


def wait_for_node_timestamp(callback_api, hostnames, timestamp, stoppable):
    _wait_for_callback(
        callback_api,
        ("Waiting for node to come up: {0}".format(', '.join(hostnames))),
        stoppable,
        _check_node_up_uptime,
        _max_waiting_time_for_node_up,
        callback_api,
        hostnames,
        timestamp
        )
    log.event.info("Node %s has come up.", hostnames)


# Wrapper is intended to get around mocking of time.time() tripping
# up nosetests, which uses it internally..
def _get_current_time():
    return int(time.time())


def _wait_for_callback(callback_api, waiting_msg, stoppable, callback,
                       max_wait, *args, **kwargs):
    epoch = _get_current_time()
    while not callback(*args, **kwargs):
        if stoppable:
            if not callback_api.is_running():
                raise PlanStoppedException(
                    "Plan execution has been stopped.")
        counter = _get_current_time() - epoch
        if counter % 60 == 0:
            log.trace.info(waiting_msg)
        if counter >= max_wait:
            raise CallbackExecutionException(
                "Node has not come up within {0} seconds".format(
                    max_wait)
            )
        time.sleep(1.0)


def _check_node_up_uptime(callback_api, hostnames, timestamp):
    reboot_time_elapsed = str(time.time() - float(timestamp))
    kwargs = {'reboot_time_elapsed': reboot_time_elapsed}
    try:
        _, errors = RebootAgent().execute_rpc_and_process_result(callback_api,
                                                        hostnames,
                                                        'core',
                                                        'has_rebooted_uptime',
                                                        action_kwargs=kwargs)
        if len(reduce_errs(errors)) == 1 and\
                           "not declared in the DDL" in reduce_errs(errors)[0]:
            return True
    except (BadRebootException, RpcExecutionException) as e:
        log.event.error("Error while waiting for node: {0}".format(str(e)))
        return False
    else:
        if errors:
            return False
        return True


def _check_node(nodes, loose, puppet_applying_catalog_valid_state):
    result = run_rpc_command(
        nodes,
        "puppet",
        "status"
    )
    valid_states = ()
    if loose:
        valid_states = ("idling", "stopped", "disabled")
    else:
        valid_states = ("idling",)
    if puppet_applying_catalog_valid_state:
        valid_states = valid_states + ("applying a catalog",)
    for node in nodes:
        if not result[node]['data']:
            return False
        if result[node]['errors']:
            return False
        if result[node]['data']['status'] not in valid_states:
            return False
    return True


def _check_node_down(nodes):
    result = run_rpc_command(nodes, "rpcutil", "ping")
    for node in nodes:
        if "No answer" not in result[node]['errors']:
            return False
    return True
