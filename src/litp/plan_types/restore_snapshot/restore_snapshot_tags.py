##############################################################################
# COPYRIGHT Ericsson 2015
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################

# Restore Snapshot tag constants

#: All tasks generated do validation checks before the plan proceeds
#: e.g. FUTURE USE
VALIDATION_TAG = "RESTORE_SNAPSHOT_VALIDATION_TAG"

#: All Tasks associated with pre-restore puppet operations
#: e.g. stop puppet, stop httpd
PREPARE_PUPPET_TAG = "RESTORE_SNAPSHOT_PREPARE_PUPPET_TAG"

#: All Tasks associated with pre-restore VCS operations
#: e.g. stop vcs
PREPARE_VCS_TAG = "RESTORE_SNAPSHOT_PREPARE_VCS_TAG"

#: pre-restore operations excluding Puppet and VCS
PRE_OPERATION_TAG = "RESTORE_SNAPSHOT_PRE_OPERATION_TAG"

#: All Tasks associated with NAS Share file-systems
#: e.g. (SFS) Plugin
NAS_FILESYSTEM_TAG = "RESTORE_SNAPSHOT_NAS_FILESYSTEM_TAG"

#: All Tasks associated with MN lvm file-systems
#: e.g. (VolMgr) Plugin
PEER_NODE_LVM_VOLUME_TAG = "RESTORE_SNAPSHOT_PEER_NODE_LVM_VOLUME_TAG"

#: All Tasks associated with MN vxvm file-systems
#: e.g. (VolMgr, Versant, MySQL) - Plugin
PEER_NODE_VXVM_VOLUME_TAG = "RESTORE_SNAPSHOT_PEER_NODE_VXVM_VOLUME_TAG"

#: MN Reboot
PEER_NODE_REBOOT_TAG = "RESTORE_SNAPSHOT_PEER_NODE_REBOOT_TAG"

#: All Tasks associated with power off procedure
#: e.g. (SAN) Plugin power off steps
PEER_NODE_POWER_OFF_TAG = "RESTORE_SNAPSHOT_PEER_NODE_POWER_OFF_TAG"

#: All Tasks associated with SAN LUNs
#: e.g. (SAN, Versant, MySQL) Plugin
SAN_LUN_TAG = "RESTORE_SNAPSHOT_SAN_LUN_TAG"

#: All Tasks associated with a post-rollback cleanup
SANITISATION_TAG = "RESTORE_SNAPSHOT_SANITISATION_TAG"

#: All Tasks associated with power on procedure
#: e.g. (SAN) Plugin power on and "wait for node" steps
PEER_NODE_POWER_ON_TAG = "RESTORE_SNAPSHOT_PEER_NODE_POWER_ON_TAG"

#: All Tasks associated procedures following power on of MN nodes
#: e.g. versant vjbackup with restore option
#: e.g. OpenDJ for importing & reconciliation of the user data
PEER_NODE_POST_POWER_ON_TAG = "RESTORE_SNAPSHOT_PEER_NODE_POST_POWER_ON_TAG"

#: All Tasks associated with MS lvm file-systems
#: e.g. (VolMgr, MySQL) Plugin
LMS_LVM_VOLUME_TAG = "RESTORE_SNAPSHOT_LMS_LVM_VOLUME_TAG"

#: MS Reboot
LMS_REBOOT_TAG = "RESTORE_SNAPSHOT_LMS_REBOOT_TAG"

RESTORE_SNAPSHOT_TAGS = (
    VALIDATION_TAG,
    PREPARE_PUPPET_TAG,
    PREPARE_VCS_TAG,
    PRE_OPERATION_TAG,
    NAS_FILESYSTEM_TAG,
    PEER_NODE_LVM_VOLUME_TAG,
    PEER_NODE_VXVM_VOLUME_TAG,
    PEER_NODE_REBOOT_TAG,
    PEER_NODE_POWER_OFF_TAG,
    SAN_LUN_TAG,
    SANITISATION_TAG,
    PEER_NODE_POWER_ON_TAG,
    PEER_NODE_POST_POWER_ON_TAG,
    LMS_LVM_VOLUME_TAG,
    LMS_REBOOT_TAG
)
