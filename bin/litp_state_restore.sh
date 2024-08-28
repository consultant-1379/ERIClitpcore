#!/bin/bash

# litp_state_restore.sh
#
# Counterpart for litp_state_backup.sh
#
# Usage:  litp_state_restore.sh <path to backup file>
#
# The file provided must exist, and the script must be run with
# "root" privileges.

python -m litp.data.backups.run restore $@
