##############################################################################
# COPYRIGHT Ericsson AB 2013
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################

from unittest import TestCase

from litp.core.model_manager import ModelManager
from litp.core.model_type import (
    Collection, Child, PropertyType, ItemType, Property, Reference
)
from litp.core.plugin_context_api import PluginApiContext


class BasePluginTestCase(TestCase):
    '''
    Base for core and puppet manager testcases
    '''
    def setUp(self):
        self.model = ModelManager()
        self.plugin_api_context = PluginApiContext(self.model)
        self.model.register_property_type(PropertyType("basic_string"))
        timestamp = PropertyType('timestamp',
                                 regex=r"^([0-9]+\.[0-9]+)|None|.*$")
        self.model.register_property_type(timestamp)
        self.model.register_property_type(PropertyType("basic_list"))
        self.model.register_item_type(
            ItemType(
                "root",
                deployments=Collection("deployment"),
                infrastructure=Child("infrastructure"),
                nodes=Collection("node"),
                snapshots=Collection("snapshot-base"),
                ms=Child("ms"),
                cluster1=Child("cluster"),
                networks=Collection("network"),
                configs=Collection("sshd-config")
             )
        )
        self.model.register_item_type(
            ItemType(
                "snapshot-base",
                timestamp=Property("timestamp")
           ),
        )
        self.model.register_item_type(
            ItemType(
                "disk-base",
           ),
        )
        self.model.register_item_type(
            ItemType(
                "disk",
                extend_item="disk-base",
                name=Property("basic_string"),
            )
        )
        self.model.register_item_type(
            ItemType(
                "system",
                system_name=Property("basic_string"),
                disks=Collection("disk-base")
            )
        )
        self.model.register_item_type(
            ItemType(
                "node",
                hostname=Property("basic_string"),
                system=Reference("system", requred=False),
           )
        )
        self.model.register_item_type(
            ItemType(
                "deployment",
                clusters=Collection("cluster-base", max_count=10),
           )
        )
        self.model.register_item_type(
            ItemType(
                "infrastructure",
                systems=Collection("system"),
           )
        )
        self.model.register_item_type(
            ItemType(
                "ms",
                hostname=Property("basic_string"),
                configs=Collection("sshd-config"),
           )
        )
        self.model.register_item_type(
            ItemType(
                "sshd-config",
           )
        )
        self.model.register_item_type(
            ItemType(
                "network",
                name=Property("basic_string"),
            )
        )
        self.model.register_item_type(
            ItemType(
                "model-item",
                name=Property("basic_string"),
            )
        )
        self.model.register_item_type(
            ItemType(
                "cluster-base",
            )
        )
        self.model.register_item_type(
            ItemType(
                "cluster",
                extend_item="cluster-base",
                dependency_list=Property('basic_list'),
                nodes=Collection('node'),
                services=Collection('clustered-service'),
            )
        )
        self.model.register_item_type(
            ItemType(
                "old-cluster",
                extend_item="cluster-base",
            )
        )
        self.model.register_item_type(
            ItemType(
                "clustered-service",
                node_list=Property('basic_list'),
                dependency_list=Property('basic_list'),
            )
        )
        self.model.create_root_item("root")
