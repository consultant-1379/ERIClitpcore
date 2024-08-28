##############################################################################
# COPYRIGHT Ericsson 2015
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################

from litp.plan_types.restore_snapshot import restore_snapshot_groups
from litp.plan_types.restore_snapshot import restore_snapshot_tags

RESTORE_SNAPSHOT_RULESET = [
    {
        "group_name": restore_snapshot_groups.VALIDATION_GROUP,
        "criteria": {
            "task_type": "CallbackTask",
            "tag_name": restore_snapshot_tags.VALIDATION_TAG},
    },
    {
        "group_name": restore_snapshot_groups.PREPARE_PUPPET_GROUP,
        "criteria": {
            "task_type": "CallbackTask",
            "tag_name": restore_snapshot_tags.PREPARE_PUPPET_TAG},
        "requires": [restore_snapshot_groups.VALIDATION_GROUP],
    },
    {
      "group_name": restore_snapshot_groups.PREPARE_VCS_GROUP,
        "criteria": {
            "task_type": "CallbackTask",
            "tag_name": restore_snapshot_tags.PREPARE_VCS_TAG},
        "requires": [restore_snapshot_groups.PREPARE_PUPPET_GROUP],
    },
    {
        "group_name": restore_snapshot_groups.PRE_OPERATION_GROUP,
        "criteria": {
            "task_type": "CallbackTask",
            "tag_name": restore_snapshot_tags.PRE_OPERATION_TAG},
        "requires": [restore_snapshot_groups.PREPARE_VCS_GROUP],
    },
    {
        "group_name": restore_snapshot_groups.NAS_FILESYSTEM_GROUP,
        "criteria": {
            "task_type": "CallbackTask",
            "tag_name": restore_snapshot_tags.NAS_FILESYSTEM_TAG},
        "requires": [restore_snapshot_groups.PRE_OPERATION_GROUP],
    },
    {
        "group_name": restore_snapshot_groups.PEER_NODE_LVM_VOLUME_GROUP,
        "criteria": {
            "task_type": "CallbackTask",
            "tag_name": restore_snapshot_tags.PEER_NODE_LVM_VOLUME_TAG},
        "requires": [restore_snapshot_groups.NAS_FILESYSTEM_GROUP],
    },
    {
        "group_name": restore_snapshot_groups.PEER_NODE_VXVM_VOLUME_GROUP,
        "criteria": {
            "task_type": "CallbackTask",
            "tag_name": restore_snapshot_tags.PEER_NODE_VXVM_VOLUME_TAG},
        "requires": [restore_snapshot_groups.PEER_NODE_LVM_VOLUME_GROUP],
    },
    {
        "group_name": restore_snapshot_groups.PEER_NODE_REBOOT_GROUP,
        "criteria": {
            "task_type": "CallbackTask",
            "tag_name": restore_snapshot_tags.PEER_NODE_REBOOT_TAG},
        "requires": [restore_snapshot_groups.PEER_NODE_VXVM_VOLUME_GROUP],
    },
    {
        "group_name": restore_snapshot_groups.PEER_NODE_POWER_OFF_GROUP,
        "criteria": {
            "task_type": "CallbackTask",
            "tag_name": restore_snapshot_tags.PEER_NODE_POWER_OFF_TAG},
        "requires": [restore_snapshot_groups.PEER_NODE_REBOOT_GROUP],
    },
    {
        "group_name": restore_snapshot_groups.SAN_LUN_GROUP,
        "criteria": {
            "task_type": "CallbackTask",
            "tag_name": restore_snapshot_tags.SAN_LUN_TAG},
        "requires": [restore_snapshot_groups.PEER_NODE_POWER_OFF_GROUP],
    },
    {
        "group_name": restore_snapshot_groups.SANITISATION_GROUP,
        "criteria": {
            "task_type": "CallbackTask",
            "tag_name": restore_snapshot_tags.SANITISATION_TAG},
        "requires": [restore_snapshot_groups.SAN_LUN_GROUP],
    },
    {
        "group_name": restore_snapshot_groups.PEER_NODE_POWER_ON_GROUP,
        "criteria": {
            "task_type": "CallbackTask",
            "tag_name": restore_snapshot_tags.PEER_NODE_POWER_ON_TAG},
        "requires": [restore_snapshot_groups.SANITISATION_GROUP],
    },
    {
        "group_name": restore_snapshot_groups.PEER_NODE_POST_POWER_ON_GROUP,
        "criteria": {
            "task_type": "CallbackTask",
            "tag_name": restore_snapshot_tags.PEER_NODE_POST_POWER_ON_TAG},
        "requires": [restore_snapshot_groups.PEER_NODE_POWER_ON_GROUP],
    },
    {
        "group_name": restore_snapshot_groups.LMS_LVM_VOLUME_GROUP,
        "criteria": {
            "task_type": "CallbackTask",
            "tag_name": restore_snapshot_tags.LMS_LVM_VOLUME_TAG},
        "requires": [restore_snapshot_groups.PEER_NODE_POST_POWER_ON_GROUP],
    },
    {
        "group_name": restore_snapshot_groups.DEFAULT_GROUP,
        "requires": [restore_snapshot_groups.LMS_LVM_VOLUME_GROUP],
        "unmatched_tasks": True,
    },
    {
        "group_name": restore_snapshot_groups.LMS_REBOOT_GROUP,
        "criteria": {
            "task_type": "CallbackTask",
            "tag_name": restore_snapshot_tags.LMS_REBOOT_TAG},
        "requires": [restore_snapshot_groups.DEFAULT_GROUP],
    }]
