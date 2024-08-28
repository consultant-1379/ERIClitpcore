##############################################################################
# COPYRIGHT Ericsson 2015
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################

# Create Snapshot group constants

#: All tasks generated do validation checks before the plan proceeds
#: e.g. FUTURE USE
VALIDATION_GROUP = "CREATE_SNAPSHOT_VALIDATION_GROUP"

#: All tasks generated that need to execute before the snapshots
#: e.g. OPenDJ plugin task to export file
PRE_OPERATION_GROUP = "CREATE_SNAPSHOT_PRE_OPERATION_GROUP"

#: All Tasks associated with MS lvm file-systems
#: e.g. (VolMgr, MySQL) Plugin
LMS_LVM_VOLUME_GROUP = "CREATE_SNAPSHOT_LMS_LVM_VOLUME_GROUP"

#: All Tasks associated with MN lvm file-systems
#: e.g. (VolMgr) Plugin
PEER_NODE_LVM_VOLUME_GROUP = "CREATE_SNAPSHOT_PEER_NODE_LVM_VOLUME_GROUP"

#: All Tasks associated with MN vxvm file-systems
#: e.g. (VolMgr, Versant, MySQL) Plugin
PEER_NODE_VXVM_VOLUME_GROUP = "CREATE_SNAPSHOT_PEER_NODE_VXVM_VOLUME_GROUP"

#: All Tasks associated with NAS Share file-systems
#: e.g. (SFS) Plugin
NAS_FILESYSTEM_GROUP = "CREATE_SNAPSHOT_NAS_FILESYSTEM_GROUP"

#: All Tasks associated with SAN LUNs
#: e.g. (SAN, Versant, MySQL) Plugin
SAN_LUN_GROUP = "CREATE_SNAPSHOT_SAN_LUN_GROUP"

# All tasks generated at the end of the snapshot sequence
# Future Use
POST_OPERATION_GROUP = "CREATE_SNAPSHOT_POST_OPERATION_GROUP"

#: All unmatched Tasks
DEFAULT_GROUP = "CREATE_SNAPSHOT_DEFAULT_GROUP"
