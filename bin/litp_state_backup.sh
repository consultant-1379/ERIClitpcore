#!/bin/bash

# litp_state_backup.sh
#
# This script creates a backup of data that may be useful to restore
# the MS to an up-to-date state after a catastrophic failure.  It
# is assumed that the disk can be restored from a snapshot of some other
# sort - this backup will just provide a small set of frequently-changing
# files that can then be restored after the snapshot has been restored,
# to bring the system closer to the state it was in when it failed.
#
# Usage:  litp_state_backup.sh <path-to-backups-directory>
#
# The directory provided must exist, and the script must be run with
# "root" privileges.  The script is intended to be run frequently
# (e.g. from cron) and will decide if anything has changed from the
# previous run and thereby avoid taking unnecessary backups.  If a backup
# is created it will be a tarball in the specified directory. At most
# five backups will be kept - when the script creates a new one it
# then checks if there are more than five and deletes the oldest ones
# as required.
#
# See LITPCDS-12927.

python -m litp.data.backups.run backup $@
