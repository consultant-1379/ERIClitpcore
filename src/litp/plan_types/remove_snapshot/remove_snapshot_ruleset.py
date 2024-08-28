##############################################################################
# COPYRIGHT Ericsson 2015
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################

from litp.plan_types.remove_snapshot import remove_snapshot_groups
from litp.plan_types.remove_snapshot import remove_snapshot_tags

REMOVE_SNAPSHOT_RULESET = [
    {
        "group_name": remove_snapshot_groups.VALIDATION_GROUP,
        "criteria": {
            "task_type": "CallbackTask",
            "tag_name": remove_snapshot_tags.VALIDATION_TAG},
    },
    {
        "group_name": remove_snapshot_groups.PRE_OPERATION_GROUP,
        "criteria": {
            "task_type": "CallbackTask",
            "tag_name": remove_snapshot_tags.PRE_OPERATION_TAG},
        "requires": [remove_snapshot_groups.VALIDATION_GROUP],
    },
    {
        "group_name": remove_snapshot_groups.LMS_LVM_VOLUME_GROUP,
        "criteria": {
            "task_type": "CallbackTask",
            "tag_name": remove_snapshot_tags.LMS_LVM_VOLUME_TAG},
        "requires": [remove_snapshot_groups.PRE_OPERATION_GROUP],
    },
    {
        "group_name": remove_snapshot_groups.PEER_NODE_LVM_VOLUME_GROUP,
        "criteria": {
            "task_type": "CallbackTask",
            "tag_name": remove_snapshot_tags.PEER_NODE_LVM_VOLUME_TAG},
        "requires": [remove_snapshot_groups.LMS_LVM_VOLUME_GROUP],
    },
    {
        "group_name": remove_snapshot_groups.PEER_NODE_VXVM_VOLUME_GROUP,
        "criteria": {
            "task_type": "CallbackTask",
            "tag_name": remove_snapshot_tags.PEER_NODE_VXVM_VOLUME_TAG},
        "requires": [remove_snapshot_groups.PEER_NODE_LVM_VOLUME_GROUP],
    },
    {
        "group_name": remove_snapshot_groups.NAS_FILESYSTEM_GROUP,
        "criteria": {
            "task_type": "CallbackTask",
            "tag_name": remove_snapshot_tags.NAS_FILESYSTEM_TAG},
        "requires": [remove_snapshot_groups.PEER_NODE_VXVM_VOLUME_GROUP],
    },
    {
        "group_name": remove_snapshot_groups.SAN_LUN_GROUP,
        "criteria": {
            "task_type": "CallbackTask",
            "tag_name": remove_snapshot_tags.SAN_LUN_TAG},
        "requires": [remove_snapshot_groups.NAS_FILESYSTEM_GROUP],
    },
    {
        "group_name": remove_snapshot_groups.DEFAULT_GROUP,
        "requires": [remove_snapshot_groups.SAN_LUN_GROUP],
        "unmatched_tasks": True,
    },
    {
        "group_name": remove_snapshot_groups.POST_OPERATION_GROUP,
        "criteria": {
            "task_type": "CallbackTask",
            "tag_name": remove_snapshot_tags.POST_OPERATION_TAG},
        "requires": [remove_snapshot_groups.DEFAULT_GROUP],
    },
    {
        "group_name": remove_snapshot_groups.FINAL_GROUP,
        "criteria": {
            "task_type": "CleanupTask"},
        "requires": [remove_snapshot_groups.POST_OPERATION_GROUP],
    }]
