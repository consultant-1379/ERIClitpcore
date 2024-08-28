##############################################################################
# COPYRIGHT Ericsson 2015
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################

from litp.plan_types.deployment_plan import deployment_plan_groups
from litp.plan_types.deployment_plan import deployment_plan_tags

DEPLOYMENT_PLAN_RULESET = [
    {
        "group_name": deployment_plan_groups.PRE_CLUSTER_GROUP,
        "criteria": [
            {
                "tag_name": deployment_plan_tags.PRE_CLUSTER_TAG,
            },
        ],
        "requires": [deployment_plan_groups.BOOT_GROUP]
    },
    {
        "group_name": deployment_plan_groups.MS_GROUP,
        "criteria": [
            {
                "tag_name": deployment_plan_tags.MS_TAG,
            },
            {
                "task_type": "RemoteExecutionTask",
                "model_item.get_ms.is_ms": True,
                "tag_name": None,
            },
            {
                "task_type": "ConfigTask",
                "node.is_ms": True,
                "tag_name": None,
            },
            {
                "task_type": "CallbackTask",
                "model_item.get_ms.is_ms": True,
                "tag_name": None,
            }],
        "unmatched_tasks": True,
    },
    {
        "group_name": deployment_plan_groups.UPGRADE_BOOT_GROUP,
        "criteria": [
            {
                "tag_name": deployment_plan_tags.UPGRADE_BOOT_TAG,
            }
        ],
        "requires": [deployment_plan_groups.PRE_NODE_CLUSTER_GROUP]
    },
    {
        "group_name": deployment_plan_groups.VXVM_UPGRADE_GROUP,
        "criteria": [
            {
                "tag_name": deployment_plan_tags.VXVM_UPGRADE_TAG,
            }
        ],
        "requires": [deployment_plan_groups.UPGRADE_BOOT_GROUP]
    },
    {
        "group_name": deployment_plan_groups.NODE_GROUP,
        "criteria": [
            {
                "tag_name": deployment_plan_tags.NODE_TAG,
            },
            {
                "task_type": "RemoteExecutionTask",
                "model_item.get_node.is_node": True,
                "tag_name": None,
            },
            {
                "task_type": "ConfigTask",
                "node.is_ms": False,
                "tag_name": None,
            },
            {
                "task_type": "CallbackTask",
                "model_item.get_node.is_node": True,
                "tag_name": None,
            }],
        "requires": [deployment_plan_groups.VXVM_UPGRADE_GROUP]
    },
    {
        "group_name": deployment_plan_groups.CLUSTER_GROUP,
        "criteria": [
            {
                "tag_name": deployment_plan_tags.CLUSTER_TAG,
            },
            {
                "task_type": "CallbackTask",
                "model_item.get_cluster.is_cluster": True,
                "tag_name": None,
            }],
        "requires": [deployment_plan_groups.NODE_GROUP]
    },
    {
        "group_name": deployment_plan_groups.BOOT_GROUP,
        "criteria":
            {
                "tag_name": deployment_plan_tags.BOOT_TAG,
            },
        "requires": [deployment_plan_groups.MS_GROUP]
    },
    {
        "group_name": deployment_plan_groups.PRE_NODE_CLUSTER_GROUP,
        "criteria": [
            {
                "tag_name": deployment_plan_tags.PRE_NODE_CLUSTER_TAG,
            },
        ],
        "requires": [deployment_plan_groups.PRE_CLUSTER_GROUP]
    },
    {
        "group_name": deployment_plan_groups.POST_CLUSTER_GROUP,
        "criteria": [
            {
                "tag_name": deployment_plan_tags.POST_CLUSTER_TAG,
            },
        ],
        "requires": [deployment_plan_groups.CLUSTER_GROUP]
    },
]
