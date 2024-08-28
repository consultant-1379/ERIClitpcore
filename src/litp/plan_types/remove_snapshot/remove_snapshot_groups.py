##############################################################################
# COPYRIGHT Ericsson 2015
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################

# Remove Snapshot group constants

#: All tasks generated do validation checks before the plan proceeds
#: e.g. (NAS, VolMgr) Plugins checks for background NAS VxVM restorations
VALIDATION_GROUP = "REMOVE_SNAPSHOT_VALIDATION_GROUP"

#: All tasks generated that need to execute before the snapshots
#: e.g. (NAS, VolMgr) Plugin test for background snapshot restoration
PRE_OPERATION_GROUP = "REMOVE_SNAPSHOT_PRE_OPERATION_GROUP"

#: All Tasks associated with MS lvm file-systems
#: e.g. (VolMgr, MySQL) Plugin
LMS_LVM_VOLUME_GROUP = "REMOVE_SNAPSHOT_LMS_LVM_VOLUME_GROUP"

#: All Tasks associated with MN lvm file-systems
#: e.g. (VolMgr) Plugin
PEER_NODE_LVM_VOLUME_GROUP = "REMOVE_SNAPSHOT_PEER_NODE_LVM_VOLUME_GROUP"

#: All Tasks associated with MN vxvm file-systems
#: e.g. (VolMgr, Versant, MySQL) Plugin
PEER_NODE_VXVM_VOLUME_GROUP = "REMOVE_SNAPSHOT_PEER_NODE_VXVM_VOLUME_GROUP"

#: All Tasks associated with NAS Share file-systems
#: e.g. (SFS) Plugin
NAS_FILESYSTEM_GROUP = "REMOVE_SNAPSHOT_NAS_FILESYSTEM_GROUP"

#: All Tasks associated with SAN LUNs
#: e.g. (SAN, Versant, MySQL) Plugin
SAN_LUN_GROUP = "REMOVE_SNAPSHOT_SAN_LUN_GROUP"

# All tasks generated at the end of the snapshot sequence
# Future Use
POST_OPERATION_GROUP = "REMOVE_SNAPSHOT_POST_OPERATION_GROUP"

#: All unmatched Tasks
DEFAULT_GROUP = "REMOVE_SNAPSHOT_DEFAULT_GROUP"

#: All Cleanup Tasks
FINAL_GROUP = "REMOVE_SNAPSHOT_FINAL_GROUP"
