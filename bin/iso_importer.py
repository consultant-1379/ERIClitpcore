#!/usr/bin/env python

import os
import sys
import argparse
import logging
import logging.config
import subprocess
import time

from litp.core.litp_logging import LitpLogger
from litp.core.iso_import import IsoImporter

from litp.enable_metrics import apply_metrics as metrics
from litp.metrics import time_taken_metrics

log = None

def run_process(command_args):
    '''
    This method will restart the litpd server after import iso has finished.
    Its meant to be used only from the spawned grandchild process from
    iso_import.py. It will handle error if any during litpd restart.
    '''
    log.trace.debug("Running process %s", command_args)
    process = subprocess.Popen(command_args, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, close_fds=True)
    out, err = process.communicate()
    if out:
        for line in out.split("\n"):
            log.trace.info('Litp service restart STDOUT: ' + line)
    if err:
        for line in err.split("\n"):
            log.trace.info('Litp service restart STDERR: ' + line)
    ret = process.returncode
    if ret:
        log.trace.error("Error running %s, return code %s",
                        command_args, ret)
    else:
        log.trace.debug("Running %s finished successfully", command_args)
    return ret


def main():
    '''
    Main method of the script. It should be called only by the grandchild
    spawned process in iso_import.py, to ensure all security checks are done
    and that this will be run only as the root user. It will run the main
    run method from IsoImporter will restart the litpd server at the end and
    and will handle any errors occurred meanwhile.
    '''
    global log

    if os.getuid():  # Not root
        print "\nPermission denied."
        sys.exit(1)

    parser = argparse.ArgumentParser(description='LITP ISO Importer')
    parser.add_argument('-l', '--logging-conf', type=str,
                        default="/etc/litp_logging.conf",
                        help='logging conf, default /etc/litp_logging.conf')
    parser.add_argument('-d', '--debug', action='store_true',
                        help='Enable debug-level logging')
    parser.add_argument('-p', '--path', type=str,
                        required=True,
                        help='Path of directory tree to be imported.')
    parser.add_argument('-m', '--management-server', dest='ms', type=str,
                        required=True,
                        help='Hostname of the MS.')
    parser.add_argument('-n', '--nodes', type=str, nargs='*', default=[],
                        help='Hostnames of managed nodes.')

    args = parser.parse_args()
    logging.config.fileConfig(args.logging_conf)
    log = LitpLogger()

    if args.debug:
        log.trace.setLevel(logging.DEBUG)

    try:
        importer = IsoImporter(args.path, args.ms, args.nodes)
        with time_taken_metrics(metrics.import_metric):
            run_result = importer.run()
            log.trace.info('ISO Importer is restarting the litpd service')

            with time_taken_metrics(metrics.restart_litp_metric):
                restart_result = run_process(['systemctl', 'restart', 'litpd.service'])

            log.trace.info('ISO Importer service restart returned %d' %
                           restart_result)
            if run_result == IsoImporter.RC_SUCCESS:
                rc = restart_result
            else:
                rc = run_result

            log.trace.info('ISO Importer is finished, exiting with %d' % rc)
            sys.exit(rc)

    except Exception as e:
        log.trace.exception('ISO Importer unhandled exception')
        log.trace.error("Error running ISO Importer, failed to complete.")
        sys.exit(-1)

if __name__ == '__main__':
    main()
