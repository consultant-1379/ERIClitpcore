##############################################################################
# COPYRIGHT Ericsson 2015
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################

MS_TAG = "DEPLOYMENT_MS_TAG"
BOOT_TAG = "DEPLOYMENT_BOOT_TAG"
UPGRADE_BOOT_TAG = "DEPLOYMENT_UPGRADE_BOOT_TAG"
VXVM_UPGRADE_TAG = "DEPLOYMENT_VXVM_UPGRADE_TAG"
NODE_TAG = "DEPLOYMENT_NODE_TAG"
CLUSTER_TAG = "DEPLOYMENT_CLUSTER_TAG"
PRE_NODE_CLUSTER_TAG = "DEPLOYMENT_PRE_NODE_CLUSTER_TAG"
PRE_CLUSTER_TAG = "DEPLOYMENT_PRE_CLUSTER_TAG"
POST_CLUSTER_TAG = "DEPLOYMENT_POST_CLUSTER_TAG"
DEPLOYMENT_PLAN_TAGS = set([MS_TAG, BOOT_TAG, UPGRADE_BOOT_TAG,
    VXVM_UPGRADE_TAG, NODE_TAG, CLUSTER_TAG, PRE_NODE_CLUSTER_TAG,
    PRE_CLUSTER_TAG, POST_CLUSTER_TAG])
