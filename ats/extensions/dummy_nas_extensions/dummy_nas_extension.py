##############################################################################
# COPYRIGHT Ericsson AB 2013
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################

from litp.core.model_type import ItemType, Property, PropertyType, Collection
from litp.core.model_type import Reference
from litp.core.extension import ModelExtension


class NasExtension(ModelExtension):
    def define_property_types(self):

        property_types = []

        property_types.append(PropertyType("mount_point",
                              regex=r"^/[A-Za-z0-9\-\._/#:\s*]+$"
                                         ))
        property_types.append(PropertyType("service_type",
                                           regex=r"^(SFS|RHEL)$"))

        property_types.append(PropertyType("export_name",
                                           regex=r"^[a-zA-Z0-9_]+$",))

        property_types.append(PropertyType("allowed_clients",
                                    regex=r"^([0-9.]+[,]?)+$",))

        property_types.append(PropertyType("nas_service_name",
                                           regex=r"^[a-zA-Z0-9\-\._]+$"))

        property_types.append(PropertyType("export_options",
                                    regex=r"[,_a-z]+",))

        property_types.append(PropertyType("mount_options",
                    regex=r"^([^,]([a-z=0-9]{1,})([\.]{0,1})([,_]?))+$",))

        property_types.append(PropertyType("management_ip",))

        property_types.append(PropertyType("vip",))

        property_types.append(PropertyType("password",
                                    regex=r"^.*$"))

        property_types.append(PropertyType("file_system",
                                    regex=r"(\w*[\w\-/])+\w"))

        return property_types

    def define_item_types(self):
        item_types = []

        item_types.append(
            ItemType("nfs-export",
                item_description="The export to be shared",
                name=Property('basic_string',
                    prop_description="The name of the export",
                    required=True),
        ))
        item_types.append(
            ItemType("nfs-service",
                item_description="The nfs service item type",
                extend_item="storage-provider-base",
                service_name=Property('basic_string',
                    prop_description="The name of the nas server",
                    required=True),
                user_name=Property('basic_string',
                    prop_description="Login details: username",
                    required=True),
                password=Property('password',
                    prop_description="Login details: password",
                    required=True),
                ip_addresses=Collection("nfs-virtual-server"),
                exports=Collection("nfs-export"),
        ))
        item_types.append(
            ItemType("nfs-virtual-server",
                item_description="The nfs-virtual-server item type represents "
                                 "a preconfigured virtual ip on the sfs "
                                 "cluster ",
                name=Property('basic_string',
                    prop_description="The name of the virtual ip",
                    required=True),
                address=Property("vip",
                    prop_description="IP address associated"
                                     " with a collection of shares",
                    required=True),

        ))
        item_types.append(
             ItemType("nfs-file-system",
                extend_item="file-system-base",
                item_description="This item represents or"
                                 " models the nfs client side",
                name=Property("basic_string",
                    prop_description="Name of the nfs-file-system",
                    required=True),
                export=Reference('nfs-export',
                    required=True),
                vip=Reference('nfs-virtual-server',
                    required=True),
                network_name=Property("basic_string",
                    prop_description="Network name assigned to"
                                     " an ip range ",
                    required=True),
                mount_point=Property("path_string",
                    prop_description="The mount point directory",
                    required=True),
                mount_options=Property("mount_options",
                    prop_description="Options connected with the NAS client",
                    required=False,
                    default='defaults'),
        ))
        return item_types

