##############################################################################
# COPYRIGHT Ericsson AB 2013
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################

from time import gmtime, localtime, strftime
import os
import re
import time
import shutil
import cherrypy
import threading
import hashlib
import json
import errno


from litp.core.constants import LIVE_MODEL
from litp.core.constants import LAST_SUCCESSFUL_PLAN_MODEL
from litp.core.litp_logging import LitpLogger
log = LitpLogger()


# FIXME: In longer term, avoid using Singleton pattern as well..
class SerializerBox(object):
    _serializer = None
    _start_lock = threading.Lock()
    _ser_thread = None

    @classmethod
    def check_serializer(cls, container):
        if not cls._serializer:
            log.event.debug("No serializer - creating one")
            cls._serializer = create_serializer(container)
            if int(cherrypy.config.get('save_window', 0)):
                cls._serializer._running = True
                cls._ser_thread = threading.Thread(
                    None, cls._serializer.run, "SerializeThread")
                cls._ser_thread.daemon = True
                cls._ser_thread.start()
        return cls._serializer

    @classmethod
    def shutdown(cls):
        if cls._serializer:
            cls._serializer.shutdown()
        if cls._ser_thread:
            cls._ser_thread.join()

    @classmethod
    def take_ticket(cls):
        if cls._serializer:
            cls._serializer.take_ticket()

    @classmethod
    def release_ticket(cls):
        if cls._serializer:
            cls._serializer.release_ticket()

    @classmethod
    def start_lock(cls):
        cls._start_lock.acquire()

    @classmethod
    def start_unlock(cls):
        cls._start_lock.release()


def create_serializer(container):
    """ Helper function for creating a serializer
        :param container: Container to be serialized
        :type container: Container
        :returns: A serializer object
        :rtype: LitpSerializer
    """
    serialiser = LitpSerializer(
        container, cherrypy.config.get('dbase_root'),
        cherrypy.config.get('dbase_last_known_link'),
        int(cherrypy.config.get('backup_interval') or 5),
        int(cherrypy.config.get('save_window') or 2),
        int(cherrypy.config.get('backups_to_keep') or 2))
    return serialiser


def shutdown_serializer():
    """ Helper function for stopping the serializer
    """
    SerializerBox().shutdown()


def start_request(container):
    """ Helper function to start a serialize request
    """
    SerializerBox().check_serializer(container)
    take_ticket()


def take_ticket():
    """ Helper function for taking a ticket in the serializer

        Taking a ticked will prevent the serializer from
        serializing information while a background task is running
    """
    SerializerBox().take_ticket()


def release_ticket():
    """ Helper function for release a ticket in the serializer

        Releasing a ticked will enable the serializer to serialize
        information again
    """
    SerializerBox().release_ticket()


def _remove_file(path):
    try:
        os.remove(path)
    except OSError as e:
        if e.errno == errno.ENOENT:
            log.trace.debug('File "%s" does not exist', path)
        else:
            log.trace.exception('Failed to remove file "%s"', path)


class LitpSerializer(object):
    def __init__(self, container, savedir, savename, backup_interval=5,
            save_window=2, backups_to_keep=2):
        """ Defines a data serializer service
            :param container: Container to be serialized
            :type container: Container
            :param savedir: Directory to save to
            :type savedir: string
            :param savename: Filename to save to
            :type savename: string
            :param backup_interval: Seconds between attempts of backup
            :type backup_interaval: integer
            :param save_window: Seconds between the saves
            :type save_window: integer
            :param backups_to_keep: Number of backups to keep
            :type backups_to_keep: integer
        """
        self.container = container
        self.savedir = savedir
        self.savename = savename
        self.backup_interval = backup_interval
        self._running = False
        self.condition = threading.Condition()
        self.tickets = 0
        self._last_saved = 0
        self.save_window = save_window
        self._backup_file_time = 0
        self._last_backup = None
        self._last_backup_cksum = None
        self.backups_to_keep = backups_to_keep

    def backup_model(self, file_abspath):
        """
        Backup the model and return the filename it was backed up to
        """
        return shutil.copy(self._save_filepath(), file_abspath)

    def backup_model_for_snapshot(self, container, file_abspath):
        """
        Backup the model with the given snapshot container.
        """
        data = container.serialize()  # Fetches the latest model
        try:
            self._save_file(file_abspath, data)
        except IOError as e:
            log.trace.info('Unable to backup snapshot model file: %s',
                    e.strerror)

    def restore_from_backup_data(self, raw_backup_json, setup_logging=True):
        log.audit.info("Restoring model from backup")
        try:
            success = self.container.do_unpickling(
                raw_backup_json,
                model_type=LAST_SUCCESSFUL_PLAN_MODEL,
                setup_logging=setup_logging
            )
        except Exception as ex:
            log.event.info("Could not restore model because no deployment "
                    "model restore file is available.")
            raise ex
        return success

    def _save_filepath(self):
        return os.path.join(self.savedir, self.savename)

    def _backup_file_age(self):
        return time.time() - self._backup_file_time

    def _saved_file_requires_backup(self, checksum):
        if self.savefile_exists():  # LAST_KNOWN_CONFIG exists
            if not self._last_backup_cksum:
                last_known_config = ''
                with open(self._save_filepath(), 'rb') as current_model:
                    # Capture sorted LAST_KNOWN_CONFIG
                    last_known_config = json.dumps(
                        json.loads(
                            current_model.read()
                        ),
                        indent=4,
                        sort_keys=True
                    )
                self._last_backup_cksum = self._checksum(last_known_config)
            if self._last_backup_cksum == checksum:
                return False

            return self._backup_file_age() > self.backup_interval
        return False

    def savefile_exists(self):
        """ Check the existence of the saved file
        """
        return self._file_exists(self._save_filepath())

    def _file_age(self, filepath):
        return time.time() - os.path.getctime(filepath)

    def _checksum(self, data):
        hasher = hashlib.md5()
        hasher.update(data)
        return hasher.hexdigest()

    def save_litp(self):
        """ Save the Litp container to the file
        """
        log.event.debug("Saving Litp")
        data = self.container.serialize()
        checksum = self._checksum(data)
        if self._saved_file_requires_backup(checksum):
            self._backup_savefile()
            self._last_backup_cksum = checksum
        try:
            self._save_file(self._save_filepath(), data)
        except IOError:
            log.event.exception("Exception in _save_file")
            log.event.critical("Could not save Litp, exiting")
            os._exit(os.EX_IOERR)
        self._last_saved = time.time()
        log.event.debug("Litp Saved")

    def load_litp(self, setup_logging=True, lkc_json=None):
        """ Load information from a previously saved file
        """
        self.container.do_unpickling(
            lkc_json or self._load_raw_json(),
            model_type=LIVE_MODEL,
            setup_logging=setup_logging
        )

    def load_plugins(self, lkc_json):
        return lkc_json.get('plugins', [])

    def load_extensions(self, lkc_json):
        return lkc_json.get('extensions', [])

    def _load_raw_json(self, filepath=None):
        '''
        Returns the JSON content of this serialiser instance's file as a Python
        dictionary.
        '''

        filepath = filepath or self._save_filepath()
        return self._load_json(filepath)

    def _backup_savefile(self):
        self._last_backup = os.path.join(self.savedir, self._backup_filename())
        shutil.copy(self._save_filepath(), self._last_backup)
        self._backup_file_time = time.time()
        self._remove_old_backups()

    def _remove_old_backups(self, backups_to_keep=2):
        """ Remove old backup config files
            At max, keep only two latest backup config files
        """
        backup_filenames = [f for f in sorted(os.listdir(self.savedir))
                                if re.match(r'^([0-9]+)\.json$', f)]
        if len(backup_filenames) > backups_to_keep:
            for json_file in backup_filenames[:-backups_to_keep]:
                _remove_file(os.path.join(*(self.savedir, json_file)))

    def _backup_filename(self):
        return strftime("%Y%m%d%H%M%S.json", localtime())

    def _tmp_filename(self):
        return strftime("tmp_%Y%m%d%H%M%S.json", gmtime())

    def _save_file(self, filename, contents):
        SerializerBox().start_lock()
        try:
            tmp_filename = self._tmp_filename()
            tmp_filename = os.path.join(
                os.path.dirname(filename), tmp_filename)
            savefile = self._open(tmp_filename, "w")
            try:
                savefile.write(contents)
                savefile.flush()
                os.fsync(savefile.fileno())
            finally:
                self._fchmod(savefile, 0644)
                savefile.close()
            os.rename(tmp_filename, filename)
        finally:
            SerializerBox().start_unlock()

    def _open(self, filename, mode):
        return open(filename, mode)

    def _fchmod(self, file_instance, mode):
        return os.fchmod(file_instance.fileno(), mode)

    def _load_file(self, filepath):
        return open(filepath).read()

    def _load_json(self, filepath):
        return json.loads(self._load_file(filepath))

    def _file_exists(self, filepath):
        return os.path.exists(filepath)

    def take_ticket(self):
        """ Take a ticket in the serializer to avoid saving
            the files while background tasks are running
        """
        self.condition.acquire()
        self.tickets += 1
        self.condition.notify()
        self.condition.release()

    def release_ticket(self):
        """ Release a ticket to allow the serializer to
            save files again
        """
        self.condition.acquire()
        self.tickets -= 1
        self.condition.notify()
        self.condition.release()

    def run(self):
        log.event.info("Starting serialize thread")
        self.condition.acquire()
        while self._running:
            if self.tickets == 0 and self._last_saved < time.time() - \
                    self.save_window:
                self.save_litp()
            elif self.tickets == 0:
                self.condition.release()
                time.sleep(self.save_window)
                self.condition.acquire()
                if self.tickets == 0:
                    self.save_litp()
            if self.tickets:
                self.condition.wait()
        self.condition.release()
        log.event.info("Ending serialize thread")

    def shutdown(self):
        """ Turn off the serializer thread
        """
        log.event.info("Shutting down serializer")
        self.condition.acquire()
        self._running = False
        self.condition.notify()
        self.condition.release()
