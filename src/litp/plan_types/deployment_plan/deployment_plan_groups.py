##############################################################################
# COPYRIGHT Ericsson 2015
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################

MS_GROUP = "DEPLOYMENT_MS_GROUP"
BOOT_GROUP = "DEPLOYMENT_BOOT_GROUP"
UPGRADE_BOOT_GROUP = "DEPLOYMENT_UPGRADE_BOOT_GROUP"
VXVM_UPGRADE_GROUP = "DEPLOYMENT_VXVM_UPGRADE_GROUP"
NODE_GROUP = "DEPLOYMENT_NODE_GROUP"
CLUSTER_GROUP = "DEPLOYMENT_CLUSTER_GROUP"
PRE_NODE_CLUSTER_GROUP = "DEPLOYMENT_PRE_NODE_CLUSTER_GROUP"
POST_CLUSTER_GROUP = "DEPLOYMENT_POST_CLUSTER_GROUP"
PRE_CLUSTER_GROUP = "DEPLOYMENT_PRE_CLUSTER_GROUP"


_group_requires_cluster_sorting = {
        MS_GROUP: False,
        BOOT_GROUP: False,
        UPGRADE_BOOT_GROUP: True,
        VXVM_UPGRADE_GROUP: True,
        NODE_GROUP: True,
        CLUSTER_GROUP: True,
        PRE_NODE_CLUSTER_GROUP: True,
        PRE_CLUSTER_GROUP: False,
        POST_CLUSTER_GROUP: False,
}

_group_requires_locking = {
        MS_GROUP: False,
        BOOT_GROUP: False,
        UPGRADE_BOOT_GROUP: True,
        VXVM_UPGRADE_GROUP: True,
        NODE_GROUP: True,
        CLUSTER_GROUP: False,
        PRE_NODE_CLUSTER_GROUP: False,
        PRE_CLUSTER_GROUP: False,
        POST_CLUSTER_GROUP: False,
}


def group_requires_cluster_sorting(group_or_groups):
    try:
        return _group_requires_cluster_sorting[group_or_groups]
    except TypeError:
        return any(_group_requires_cluster_sorting[group_name] for
            group_name in group_or_groups)
    except KeyError:
        raise ValueError(
            "Unkown group: \"{group}\"".format(group=group_or_groups)
        )


def is_node_group(group_or_groups):
    try:
        return _group_requires_locking[group_or_groups]
    except TypeError:
        return any(_group_requires_locking[group_name] for
            group_name in group_or_groups)
    except KeyError:
        raise ValueError(
            "Unkown group: \"{group}\"".format(group=group_or_groups)
        )
