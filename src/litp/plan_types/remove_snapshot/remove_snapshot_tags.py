##############################################################################
# COPYRIGHT Ericsson 2015
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################

# Remove Snapshot tag constants

#: All tasks generated do validation checks before the plan proceeds
#: e.g. (NAS, VolMgr) Plugins checks for background NAS VxVM restorations
VALIDATION_TAG = "REMOVE_SNAPSHOT_VALIDATION_TAG"

#: All tasks generated that need to execute before the snapshots
#: e.g. (NAS, VolMgr) Plugin test for background snapshot restoration
PRE_OPERATION_TAG = "REMOVE_SNAPSHOT_PRE_OPERATION_TAG"

#: All Tasks associated with MS lvm file-systems
#: e.g. (VolMgr, MySQL) Plugin
LMS_LVM_VOLUME_TAG = "REMOVE_SNAPSHOT_LMS_LVM_VOLUME_TAG"

#: All Tasks associated with MN lvm file-systems
#: e.g. (VolMgr) Plugin
PEER_NODE_LVM_VOLUME_TAG = "REMOVE_SNAPSHOT_PEER_NODE_LVM_VOLUME_TAG"

#: All Tasks associated with MN vxvm file-systems
#: e.g. (VolMgr, Versant, MySQL) Plugin
PEER_NODE_VXVM_VOLUME_TAG = "REMOVE_SNAPSHOT_PEER_NODE_VXVM_VOLUME_TAG"

#: All Tasks associated with NAS Share file-systems
#: e.g. (SFS) Plugin
NAS_FILESYSTEM_TAG = "REMOVE_SNAPSHOT_NAS_FILESYSTEM_TAG"

#: All Tasks associated with SAN LUNs
#: e.g. (SAN, Versant, MySQL) Plugin
SAN_LUN_TAG = "REMOVE_SNAPSHOT_SAN_LUN_TAG"

# All tasks generated at the end of the snapshot sequence
# Future Use
POST_OPERATION_TAG = "REMOVE_SNAPSHOT_POST_OPERATION_TAG"

REMOVE_SNAPSHOT_TAGS = (
    VALIDATION_TAG,
    PRE_OPERATION_TAG,
    LMS_LVM_VOLUME_TAG,
    PEER_NODE_LVM_VOLUME_TAG,
    PEER_NODE_VXVM_VOLUME_TAG,
    NAS_FILESYSTEM_TAG,
    SAN_LUN_TAG,
    POST_OPERATION_TAG
)
