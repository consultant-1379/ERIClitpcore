import os
import json
import errno
import fcntl
import time

from litp.core.litp_logging import LitpLogger
from litp.core.model_item import ModelItem
from litp.service.utils import update_maintenance


log = LitpLogger()
INITIATED_MANUALLY = 'user'
INITIATED_IMPORT_ISO = 'import_iso'


def initialize_maintenance(model_manager):
    '''
    This method will be called at litpd restart time. Depending on the content
    of the import iso state file, it will call the enter_maintenance_mode
    method or will modify the model with the exit_maintenance_mode method
    to leave it.
    '''

    maintenance_item = model_manager.get_item('/litp/maintenance')
    was_enabled = maintenance_item.enabled == 'true'

    # At startup, we restore our maintenance mode setting from the saved model
    # state.  If we were previously in maintenance mode then we need to
    # decide whether to stay in it or resume normal operation.  We do that
    # by looking at the state of the maintenance job as saved in the
    # StateFile (see below).

    # Right now, we # have only two ways to go - remain in maintenance mode
    # or resume normal operation.  We should perhaps introduce a third "error"
    # mode, in which we would retur 500 rather than 503.  So, we would remain
    # in maintenance mode only if the job status was "Running".  We would
    # resume normal operations for "Done" or "None", and we would enter
    # error mode for "Failed" or "Unknown".  But for now, we use maintenance
    # mode for errors.

    # States in which we should remain in maintenance mode

    states_to_remain = [
        StateFile.STATE_RUNNING,
        StateFile.STATE_FAILED,
        StateFile.STATE_UNKNOWN,
        StateFile.STATE_NONE,
    ]

    # States in which we should exit maintenance mode

    states_to_exit = [
        StateFile.STATE_DONE,
    ]

    if was_enabled:
        state = StateFile.read_state()
        log.trace.info("Maintenance job state: %s", state)
        if state in states_to_remain:
            to_be_enabled = True
        elif state in states_to_exit:
            to_be_enabled = False
        else:
            log.trace.error('Unknown maintenance job state: "%s"' % state)
            to_be_enabled = True
    else:
        to_be_enabled = False

    log.trace.info("Maintenance mode: was_enabled: %s, to_be_enabled: %s" % \
                    (was_enabled, to_be_enabled))
    if to_be_enabled:
        enter_maintenance_mode(model_manager)
    else:
        exit_maintenance_mode(model_manager)
        StateFile.remove_file()


def exit_maintenance_mode(model_manager):
    '''
    Will leave the maintenance mode
    '''
    _set_maintenance_mode(model_manager, 'false')


def enter_maintenance_mode(model_manager, initiator=INITIATED_IMPORT_ISO):
    '''
    Will set LITP into maintenance mode and use the parameter to report
    the reason why maintenance mode was enabled.
    '''
    _set_maintenance_mode(model_manager, 'true')
    set_maintenance_initiator(model_manager, initiator)


def _set_maintenance_mode(model_manager, value):
    log.trace.debug('Setting maintenance mode = %s', value)

    update_result = model_manager.update_item(
                        '/litp/maintenance', enabled=value)

    if not isinstance(update_result, ModelItem):
        # If the update failed, we should get an error.
        # Log it and return it.
        log.trace.debug(
            'Errors updating maintenance item: %s' % update_result)
        return update_result

    update_maintenance(update_result)


def set_maintenance_initiator(model_manager, initiator):
    '''
    Will set in the model the reason the maintenance mode entered
    '''

    log.trace.debug('Setting maintenance initiator = %s', initiator)

    model_manager.get_item('/litp/maintenance').set_property('initiator',
                                                            initiator)
    return model_manager.get_item('/litp/maintenance')


class StateFile(object):
    '''
    This class contains the methods to write and read the state file dedicated
    to import iso. Contains a set of possible statuses and read method that
    will interpret its contents.
    '''
    FILENAME = '/var/lib/litp/core/maintenance_job_state.txt'

    STATE_STARTING = 'Starting'     # About to start job (still not launched)
    STATE_RUNNING = 'Running'       # Job is still happily running
    STATE_DONE = 'Done'             # Job completed successfully
    STATE_NONE = 'None'             # Job? What job?
    STATE_FAILED = 'Failed'         # Job failed
    STATE_UNKNOWN = 'Unknown'       # Zoikes!  State file corrupt?

    @classmethod
    def read_state(cls):
        '''
        Read method for maintenance_job_state.txt. Will interpret its contents
        and will return an proper return value.
        '''

        for i in range(3):
            try:
                with open(cls.FILENAME, 'r') as f:
                    fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    data = json.load(f)
                break
            except ValueError as e:
                log.trace.exception(e)
                return cls.STATE_UNKNOWN
            except IOError as e:
                # Check if the error due to another process accessing the file.
                if e.errno in (errno.EACCES, errno.EAGAIN):
                    if 2 == i:
                        log.trace.exception(e)
                        return cls.STATE_UNKNOWN
                    time.sleep(1)
                elif e.errno == errno.ENOENT:
                    log.trace.debug('File "%s" does not exist' % cls.FILENAME)
                    return cls.STATE_NONE
                else:
                    log.trace.exception(e)
                    return cls.STATE_UNKNOWN

        try:
            pid = data['pid']
            state = data['state']
        except KeyError as e:
            log.trace.exception(e)
            return cls.STATE_UNKNOWN

        log.trace.debug('read_state: pid: %d, state: "%s"' % (pid, state))

        if state in [cls.STATE_DONE, cls.STATE_FAILED]:
            return state

        if state == cls.STATE_RUNNING:
            try:
                os.kill(pid, 0)
            except OSError:
                log.trace.debug('"Running", but pid is dead => "Failed"')
                return cls.STATE_FAILED
            else:
                log.trace.debug('Still running.')
                return cls.STATE_RUNNING

        return cls.STATE_UNKNOWN

    @classmethod
    def write_state(cls, state):
        '''
        Write method for maintenance_job_state.txt. Will only accept preset
        values.
        '''
        pid = os.getpid()
        log.trace.debug('write_state: pid: %d, state: "%s"' % (pid, state))
        data = {
            'pid': pid,
            'state': state,
        }

        with open(cls.FILENAME, 'w') as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            json.dump(data, f)

    @classmethod
    def remove_file(cls):
        '''
        Remove method for maintenance_job_state.txt
        '''

        # Silently remove the file - ie. do nothing if it doesn't exist
        try:
            os.remove(cls.FILENAME)
            log.trace.info('Removed state file %s', cls.FILENAME)
        except OSError as e:
            if e.errno == errno.ENOENT:
                log.trace.debug('State file %s does not exist', cls.FILENAME)
            else:
                log.trace.exception('Failed to remove state file %s', \
                                    cls.FILENAME)
