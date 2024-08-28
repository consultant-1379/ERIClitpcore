##############################################################################
# COPYRIGHT Ericsson AB 2013
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################

import socket

from litp.core.plan import Plan
from litp.core.model_type import ItemType, Property, PropertyType, \
    Reference, Collection, RefCollection, Child, View
from litp.core.extension import ModelExtension
from litp.core.validators import ItemValidator, ValidationError, \
    IPAddressValidator, NetworkValidator, IsNotDigitValidator, \
    IntRangeValidator, DirectoryExistValidator, ZeroAddressValidator, \
    IPv6AddressAndMaskValidator, NotEmptyStringValidator, IntValidator, \
    RestrictedPropertiesValidator
from litp.core.exceptions import ViewError, CyclicGraphException
from litp.core.topsort import topsort


class CoreExtension(ModelExtension):
    """Provides LITP Core Property and Model Types."""

    base_type_description = (" A base item type is an item type defined in "
    "the LITP Core extension which is designed to be extended by a more "
    "specific item type in a Model Extension. A base item type does not "
    "typically contain any properties.")

    DISALLOWED_SERVICES_GLOBAL = ['puppet', 'mcollective', 'network',
                                  'puppetserver', 'puppetserver_monitor']
    DISALLOWED_SERVICES_VALIDATION_MESSAGE = 'Service "%s" is managed by LITP'

    def define_property_types(self):
        return [
            PropertyType("any_string", regex=r"^.*$"),
            PropertyType("basic_string", regex=r"^[a-zA-Z0-9\-\._]+$"),
            PropertyType("basic_list",
                         regex=r"^[a-zA-Z0-9\-\._]*(,[a-zA-Z0-9\-\._]+)*$"),
            PropertyType("basic_list_non_empty",
                         regex=r"^[a-zA-Z0-9\-\._]+(,[a-zA-Z0-9\-\._]+)*$"),
            PropertyType("basic_boolean", regex=r"^(true|false)$"),
            PropertyType("basic_percent",
                          regex=r"^\d+$"),
            PropertyType("digit", regex=r"^[0-9]$"),
            PropertyType("integer", regex=r"^[0-9]+$",
                validators=[IntValidator()]),
            PropertyType("positive_integer", regex=r"^[1-9][0-9]*$",
                validators=[IntValidator()]),
            PropertyType("posix_name",
                         regex=r"^[A-Za-z0-9_][A-Za-z0-9_-]{0,30}$"),
            PropertyType("path_string",
                         regex=r"^/[A-Za-z0-9\-\._/#:\s*]+$"),
            PropertyType("path_string_command",
                         regex=r"^/[A-Za-z0-9\-\._/#:\s=]+$"),
            PropertyType("path_string_incl_root",
                         regex=r"^/|/[A-Za-z0-9\-\._/#:\s*]+$"),
            PropertyType("file_path_string",
                         regex=r"^[A-Za-z0-9\-\._/#:\s*]+$"),
            PropertyType("file_mode", regex=r"^[0-7]?[0-7][0-7][0-7]$"),
            PropertyType("mac_address",
                         regex=r"^([a-fA-F0-9]{2}(:)){5}([a-fA-F0-9]{2})$"),
            PropertyType("date_format", regex=r"^([-]?[%]+[Y|m|d|s])*$"),
            PropertyType("network", regex=r"^[0-9\./]+$",
                validators=[NotEmptyStringValidator(), NetworkValidator(),
                    ZeroAddressValidator()]),
            PropertyType("ipv4_address", regex=r"^[0-9\.]+$",
                         regex_error_desc='IPv4 Address must be specified',
                         validators=[IPAddressValidator("4")]),
            PropertyType("ipv6_address", validators=[IPAddressValidator("6")]),
            PropertyType("ipv4_or_ipv6_address",
                         validators=[IPAddressValidator("both")]),
            PropertyType("ipv6_address_and_mask",
                         validators=[IPv6AddressAndMaskValidator()]),
            PropertyType("port", regex=r"^[0-9]+$"),
            PropertyType("disk_size", regex=r"^[1-9][0-9]{0,}[MGT]$"),
            PropertyType("hostname",
                         regex=r"^([a-zA-Z0-9][a-zA-Z0-9\-]"\
                         "{0,61}[a-zA-Z0-9])$",
                         validators=[IsNotDigitValidator()]),
            PropertyType("domain",
                         regex=r"^[a-zA-Z][a-zA-Z0-9\-]+(\.[a-zA-Z0-9\-]+)+$",
                         validators=[IsNotDigitValidator()]),
            PropertyType("os_version", regex=r"^(rhel6|rhel7)$"),
            PropertyType("disk_uuid", regex=r"^[a-zA-Z0-9_][a-zA-Z0-9_-]*$"),
            PropertyType("kopts_post", regex=r"^[^=]*[=]{1,1}[^=]*$"),
            PropertyType("plan_state", regex=(r"^(" + Plan.RUNNING +
                                              "|" + Plan.STOPPED +
                                              ")$")),
            PropertyType('node_id', validators=[
                IntRangeValidator(min_value=1, max_value=2047)]),
            PropertyType('status_interval', regex=r'^[0-9]+', validators=[
                IntRangeValidator(min_value=10, max_value=3600)]),
            PropertyType('status_timeout', regex=r'^[0-9]+', validators=[
                IntRangeValidator(min_value=10, max_value=3600)]),
            PropertyType('timestamp', regex=r"^([0-9]+\.[0-9]+)|None|.*$"),
            PropertyType('ha_manager', regex=r"^(cmw|vcs|)$"),
            PropertyType("comma_separated_alias_names",
                regex=r"^"
                    r"([a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9\-]*[a-zA-Z0-9])(\."
                    r"([A-Za-z0-9]|[A-Za-z0-9][A-Za-z0-9\-]*[A-Za-z0-9]))*"
                    r"(,"
                    r"([a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9\-]*[a-zA-Z0-9])(\."
                    r"([A-Za-z0-9]|[A-Za-z0-9][A-Za-z0-9\-]*[A-Za-z0-9]))*)*$",
                validators=[IsNotDigitValidator()]),
            PropertyType("service_name", regex=r"^[a-zA-Z0-9\-\._]+$",
                validators=[RestrictedPropertiesValidator(
                    CoreExtension.DISALLOWED_SERVICES_GLOBAL,
                    CoreExtension.DISALLOWED_SERVICES_VALIDATION_MESSAGE)]),
            PropertyType("checksum_hex_string", regex=r"^([a-fA-F0-9]{32})$"),
            PropertyType("prepare_path", regex=r"^/$"),
            PropertyType("prepare_actions", regex=r"^all$")
        ]

    def define_item_types(self):
        return [
            ItemType(
                "root",
                item_description="This is the root-level item type. An item "
                                 "of this type is automatically created in "
                                 "the model when LITP is started. It has no "
                                 "properties but contains collections of "
                                 "deployments, plans and snapshots in "
                                 "addition to child item software, "
                                 "infrastructure and the management server.",
                ms=Child("ms", required=True),
                plans=Collection("plan", max_count=1,),
                deployments=Collection("deployment", max_count=99),
                software=Child("software", required=True),
                infrastructure=Child("infrastructure", required=True),
                snapshots=Collection("snapshot-base", max_count=1000),
                litp=Collection("litp-service-base"),
            ),
            ItemType(
                "software",
                item_description="This item type, which represents a "
                                 "container for software entities in the "
                                 "deployment model, is a child of root. It is "
                                 "automatically created in the model when "
                                 "LITP is started.",
                profiles=Collection("profile"),
                runtimes=Collection("runtime-entity"),
                deployables=Collection("deployable-entity"),
                items=Collection("software-item"),
                services=Collection("service-base"),
                images=Collection("image-base"),
            ),
            ItemType(
                "runtime-entity",
                item_description="Base runtime entity item.",
                start_command=Property(
                    "path_string",
                    prop_description="Command to start runtime entity"),
                stop_command=Property(
                    "path_string",
                    prop_description="Command to stop runtime entity"),
                status_command=Property(
                    "path_string",
                    prop_description="Command to healthcheck runtime entity"),
                cleanup_command=Property(
                    "path_string",
                    default="/bin/true",
                    prop_description="Command to cleanup runtime entity"),
                user=Property(
                    "posix_name",
                    prop_description="Unix user name to run as"),
                packages=RefCollection("software-item")
            ),
            ItemType(
                "deployable-entity",
                item_description="This item type represents an entity that "
                                 "runs within the application space.",
            ),
            ItemType(
                "software-item",
                item_description="This is the base item type for software." + \
                                 CoreExtension.base_type_description,
            ),
            ItemType(
                "ha-config-base",
                item_description="Base ha-config item." + \
                                 CoreExtension.base_type_description,
            ),
            ItemType(
                "ha-config",
                item_description="This item type represents high availability "
                "configuration for other resources. No reconfiguration actions"
                " are currently supported for this item type.",
                extend_item="ha-config-base",
                status_interval=Property(
                    'status_interval',
                    prop_description="Value, in seconds, of the interval "
                                      "between status checks"),
                status_timeout=Property(
                    'status_timeout',
                    prop_description="Value, in seconds, of the max "
                                      "duration of a status check"),
            ),
            ItemType(
                "ha-service-config",
                item_description="This item type represents high availability "
                "configuration for services (application resources). "
                "Reconfiguration actions are currently supported for some "
                "properties of this item type.",
                extend_item="ha-config",
                restart_limit=Property(
                    'integer',
                    prop_description="Number of times an attempt should be "
                                      "made to restart a failed application"),
                startup_retry_limit=Property(
                    'integer',
                    prop_description="Number of times an attempt should be "
                                      "made to start an application"),
                service_id=Property(
                    'basic_string',
                    updatable_rest=False,
                    prop_description="The item ID of the service to which "
                                      "this configuration is related. This "
                                      "property is mandatory if more than one "
                                      "service is present in the VCS cluster"),
                dependency_list=Property(
                    'basic_list',
                    updatable_rest=False,
                    prop_description="A comma-separated list of the service "
                                      "item IDs which define the dependencies "
                                      "of the service to which this "
                                      "configuration is related"),
                fault_on_monitor_timeouts=Property(
                    'integer',
                    required=True,
                    default="4",
                    prop_description="The number of times in a row the "
                                     "monitor process times out without "
                                     "declaring a resource offline. If it is "
                                     "set to 0, it is turned off. If it is "
                                     "set to 1, each monitor timeout is "
                                     "treated as a resource fault."),
                tolerance_limit=Property(
                    'integer',
                    required=True,
                    default="0",
                    prop_description="The number of times the monitor process "
                                     "returns an offline status before "
                                     "declaring a resource offline."),
                clean_timeout=Property(
                    'positive_integer',
                    required=True,
                    default="60",
                    prop_description="The maximum time, in seconds, in which "
                                     "the cleanup function must complete "
                                     "before it is terminated."),
            ),
            ItemType(
                "service-base",
                item_description="This is the base item type for a service "
                                 "(an application resource)." + \
                                 CoreExtension.base_type_description,
            ),
            ItemType(
                "service",
                item_description="This item type represents a service (an "
                                  "application resource). Some limited "
                                  "reconfiguration actions are currently "
                                  "supported for this item type.",
                extend_item="service-base",
                service_name=Property(
                    'service_name',
                    required=True,
                    prop_description="Name of the service to be called to "
                                                "start / stop / status."),
                start_command=Property(
                    "path_string",
                    prop_description="Command to start service."),
                stop_command=Property(
                    "path_string",
                    prop_description="Command to stop service."),
                status_command=Property(
                    "path_string",
                    prop_description="Command to healthcheck service."),
                cleanup_command=Property(
                    "path_string_command",
                    default="/bin/true",
                    prop_description="Command to cleanup runtime entity"),
                packages=RefCollection("software-item")
            ),
            ItemType(
                "profile",
                item_description="Base profile item type." + \
                                 CoreExtension.base_type_description,
            ),

            # cobbler plugin / core item type
            ItemType(
                "os-profile",
                extend_item="profile",
                item_description="This item type represents an OS (Operating "
                                 "System) profile for a node. You cannot "
                                 "update items of this type; if you attempt "
                                 "to update it, plan validation fails.",
                validators=[DirectoryExistValidator()],
                name=Property(
                    "basic_string",
                    required=True,
                    prop_description="Name of profile.",
                    updatable_rest=False,
                ),
                arch=Property(
                    "basic_string",
                    required=True,
                    default="x86_64",
                    prop_description="Architecture of OS.",
                    updatable_rest=False,
                ),
                breed=Property(
                    "basic_string",
                    required=True,
                    default="redhat",
                    prop_description="Breed of OS.",
                    updatable_rest=False,
                ),
                version=Property(
                    "os_version",
                    required=True,
                    default="rhel6",
                    prop_description="Version of OS profile.",
                    updatable_rest=False,
                ),
                path=Property(
                    "path_string",
                    required=True,
                    prop_description="Path to OS image.",
                    updatable_rest=False,
                ),
                kopts_post=Property(
                    "kopts_post",
                    required=True,
                    default="console=ttyS0,115200",
                    prop_description="OS post-kernel options.",
                    updatable_rest=False,
                ),
            ),

            ItemType(
                "network-interface",
                item_description="This is the base item type"
                                 " for a network interface.",
                network_name=Property(
                    "basic_string",
                    required=False,  # network_name is required if
                    # ipaddress/ipv6address property is set
                    prop_description="Network this interface's IP "
                        "address(es) belongs to.",
                ),
                ipaddress=Property(
                    "ipv4_address",
                    required=False,
                    site_specific=True,
                    prop_description="IP v4 address for this net interface.",
                ),
                ipv6address=Property(
                    "ipv6_address_and_mask",
                    site_specific=True,
                    prop_description="IP v6 address for this net interface.",
                    required=False,
                ),
                ipv6_autoconf=Property(
                    "basic_boolean",
                    required=False,
                    updatable_rest=True,
                    updatable_plugin=False,
                    prop_description="Enable automatic IPv6 configuration",
                ),
            ),

            ItemType(
                "system",
                item_description="This is the base item type for deployment "
                                 "model items that model system hardware or "
                                 "virtual machines.",
                serial=Property(
                    "basic_string",
                    prop_description="Serial number of system."
                ),
                system_name=Property(
                    "basic_string",
                    prop_description="Name of system.",
                    required=True,
                    site_specific=True
                ),
                disks=Collection("disk-base"),
                controllers=Collection("controller-base", require="disks"),
            ),

            ItemType(
                "bmc-base",
                item_description="This is the base item type for a BMC "
                                 "(Baseboard Management Controller)." + \
                                 CoreExtension.base_type_description,
            ),
            ItemType(
                "disk-base",
                item_description="Base disk item type." + \
                                 CoreExtension.base_type_description,
                disk_fact_name=View(
                    "any_string",
                    CoreExtension.gen_disk_fact_name,
                    view_description='Fact name for the disk.'
                ),
            ),

            ItemType(
                "blade",
                item_description="This item type represents a blade"
                                 " system, where a blade is a self-contained"
                                 " server that collectively fits into an "
                                 " enclosure with other blades.",
                extend_item="system",
                bmc=Child("bmc-base"),
            ),

            ItemType(
                "blade-rack",
                item_description="This item type represents a collection"
                                 " of blades and can be used to model multiple"
                                 " blade items under"
                                 " infrastructure/systems. This item type"
                                 " is not currently used in LITP.",
                extend_item="system",
                blades=Collection("blade"),
            ),

            # storage plugin item types
            ItemType(
                "disk",
                extend_item="disk-base",
                item_description="This is the base item type for a disk.",
                bootable=Property(
                    "basic_boolean",
                    default="false",
                    updatable_rest=False,
                    prop_description="Set to true if this disk is the system" \
                    " bootup device. This must be set for exactly one disk."
                    ),
                name=Property(
                    "basic_string",
                    prop_description="Device name of this disk.",
                    updatable_rest=False,
                    required=True,
                ),
                size=Property(
                    "disk_size",
                    required=True,
                    updatable_rest=True,
                    prop_description="Size of this disk.",
                ),
                uuid=Property(
                    "disk_uuid",
                    prop_description="UUID of this disk.",
                    updatable_rest=True,
                    required=True,
                    site_specific=True
                ),
                disk_part=Property("basic_boolean",
                    prop_description='Disk has partitions.',
                    updatable_plugin=True,
                    updatable_rest=False,
                    required=False,
                    default="false",
                ),
            ),
            ItemType(
                "scsi-block-device",
                item_description="This is the base item type for a"
                                 " SCSI device.",
                extend_item="disk",
            ),
            ItemType(
                "sata-block-device",
                item_description="This is the base item type for a"
                                 " SATA device.",
                extend_item="disk",
            ),
            ItemType(
                "snapshot-base",
                item_description=("This item type is automatically "
                                "created by LITP when a deployment "
                                "snapshot is taken. The timestamp "
                                "property indicates when the "
                                "snapshot was created."),
                timestamp=Property('timestamp',
                            prop_description='Snapshot creation timestamp.',
                            required=False,
                            updatable_rest=False),
                reboot_issued_at=Property('timestamp',
                            prop_description='Timestamp in which reboot to'\
                            ' the nodes was issued',
                            required=False,
                            updatable_rest=False,
                            updatable_plugin=True),
                rebooted_clusters=Property('basic_list',
                            prop_description='Clusters already rebooted'\
                            ' by restore snapshot',
                            required=False,
                            updatable_rest=False,
                            updatable_plugin=True),
                active=Property('basic_boolean',
                            prop_description='Whether this is the active '\
                            'snapshot.',
                            required=False,
                            updatable_rest=False,
                            default='true'),
                force=Property('basic_boolean',
                            prop_description='Whether remove or restore '\
                            'snapshot actions are forced.',
                            required=False,
                            updatable_rest=False,
                            updatable_plugin=False,
                            default='false')
            ),
            ItemType(
                "deployment",
                item_description="This item type represents a deployment, "
                                 "where a deployment is a group of LITP "
                                 "model items representing a collection of "
                                 "clusters and/or individual nodes within a "
                                 "logical deployment on a customer site.",
                clusters=Collection("cluster-base", min_count=1, max_count=50),
                ordered_clusters=View(
                    "basic_list",
                    CoreExtension.get_ordered_clusters,
                    view_description="List of cluster items sorted "
                                     "based upon defined dependencies."),
                in_restore_mode=Property(
                    "basic_boolean",
                    prop_description="Flag property that can be used to "
                                     "determine if in BUR restore mode. "
                                     "Use case is that BUR set this to true "
                                     "before plan creation, and to false "
                                     "before running the plan. There is no "
                                     "enforcement of this behaviour so "
                                     "any plugin should cross validate "
                                     "against the state of the deployment "
                                     "item.",
                    default="false",
                    updatable_rest=True,
                ),
            ),
            ItemType(
                "cluster-base",
                item_description="This is the base item type for a cluster "
                                 "of nodes." + \
                                 CoreExtension.base_type_description,
            ),
            ItemType(
                "cluster",
                extend_item="cluster-base",
                item_description="This item type represents a cluster "
                                 "of nodes.",
                nodes=Collection("node", min_count=1, max_count=50),
                services=Collection("clustered-service", require="software"),
                software=RefCollection("software-item", require="nodes"),
                managed_files=RefCollection("managed-file-base"),
                ha_manager=Property(
                    "ha_manager",
                    prop_description="Type of ha_manager to use.",
                    updatable_plugin=True,
                    updatable_rest=False
                ),
                configs=Collection("cluster-config", require="nodes"),
                dependency_list=Property(
                    "basic_list",
                    prop_description="A comma-separated list of the cluster "
                        "item_ids that are dependencies of this cluster. "
                        "Tasks associated with these dependent clusters "
                        "are ordered before the tasks associated with "
                        "this cluster."
                ),
            ),
            ItemType(
                "cluster-config",
                item_description="This item type represents the "
                                 "configuration applied to all the nodes "
                                 "within a cluster.",
            ),
            ItemType(
                "clustered-service",
                item_description="This item type represents a container "
                                 "for items that are required to offer an "
                                 "HA-managed application which runs on one "
                                 "or more nodes in a cluster.",
                nodes=View(
                    "node",
                    CoreExtension.resolve_clustered_service_nodes,
                    view_description="List of node items "
                                     "assigned to this cluster-service."),
                node_list=Property("basic_list_non_empty",
                                   prop_description="A comma separated list "
                                   "of the node item_ids assigned to the "
                                   "clustered-service. Note that the order "
                                   "of nodes in this list may be important to "
                                   "the plugin that is using this item. "
                                   "Please consult the documentation of the "
                                   "plugin that will be using this item for "
                                   "further details.", required=True),
                runtimes=Collection("runtime-entity"),
                dependencies=View(
                    "clustered-service",
                    CoreExtension.resolve_clustered_service_dependencies,
                    view_description="List of cluster-service dependencies."),
                dependency_list=Property("basic_list",
                                         prop_description="A comma separated "
                                         "list of the clustered-service "
                                         "item_ids that are dependencies."),
                active=Property(
                    "positive_integer",
                    required=True,
                    prop_description="Active nodes"),
                standby=Property(
                    "integer",
                    required=True,
                    prop_description="Standby nodes"),
                name=Property("basic_string",
                              required=True,
                              prop_description="Name of clustered service"),
                applications=RefCollection("service"),
                ha_configs=Collection("ha-config-base"),
            ),
            ItemType(
                "storage",
                item_description="This single-instance item type is the type "
                                 "of the only item in "
                                 "/infrastructure/storage. It represents a "
                                 "container for storage configuration items.",
                storage_profiles=Collection("storage-profile-base"),
                nfs_mounts=Collection("file-system-base"),
                managed_files=Collection("managed-file-base"),
                storage_providers=Collection("storage-provider-base"),
            ),
            ItemType(
                'storage-profile-base',
                item_description="This is the base item type for a"
                                 " storage profile." + \
                CoreExtension.base_type_description,
            ),
            ItemType(
                "node",
                item_description="This item type represents a single compute "
                                 "node (that is, a physical or virtual "
                                 "computer system combined with an operating "
                                 "system).",
                hostname=Property(
                    "hostname",
                    required=True,
                    prop_description="hostname for this node.",
                    site_specific=True,
                    updatable_rest=False
                ),
                domain=Property(
                    "domain",
                    prop_description="domain for this node.",
                    site_specific=True
                ),
                os=Reference(
                    "os-profile",
                    require="system",
                    required=True
                ),
                system=Reference(
                    "system",
                    required=True,
                    exclusive=True
                ),
                items=RefCollection("software-item",
                                    require="file_systems"),
                services=RefCollection("service-base",
                                       require="file_systems"),
                file_systems=RefCollection(
                           "file-system-base",
                           require="storage_profile"
                ),
                managed_files=RefCollection("managed-file-base"),
                storage_profile=Reference(
                    "storage-profile-base",
                    require="routes",
                    required=True
                ),
                routes=RefCollection(
                    "route-base",
                    require="network_interfaces"
                ),
                network_interfaces=Collection(
                    "network-interface",
                    require="os",
                    min_count=1
                ),
                node_id=Property(
                    "node_id",
                    prop_description="Unique identifier for this node.",
                ),
                upgrade=Child("upgrade",
                              required=False),
                configs=Collection("node-config",
                                   require="file_systems"),
                is_locked=Property("basic_boolean",
                    default="false",
                    prop_description="Set to true if this node is locked.",
                    required=True,
                    updatable_rest=False,
                    updatable_plugin=False,
                )
            ),
            ItemType(
                "node-config",
                item_description="This is the base item type for a "
                                 "node-specific configuration." + \
                                 CoreExtension.base_type_description,
            ),
            ItemType(
                "controller-base",
                item_description="This is the base item type for a node "
                                 "controller." + \
                                 CoreExtension.base_type_description,
            ),
            ItemType(
                "storage-provider-base",
                item_description="Base item type for a storage provider." + \
                                 CoreExtension.base_type_description,
            ),
            ItemType(
                "file-system-base",
                item_description="This is the base item type for a file"
                                 " system." + \
                                 CoreExtension.base_type_description,
            ),
            ItemType(
                "managed-file-base",
                item_description="This is the base item type for managed "
                                 "files." + \
                                 CoreExtension.base_type_description,
            ),
            ItemType(
                "ms-service",
                deprecated=True,
                extend_item="service-base",
                item_description="Base type for services (e.g. cobbler) "
                "modelled on the MS.",
            ),
            ItemType(
                "ms",
                item_description="This item type is a child of root. It "
                                 "represents the management server and is "
                                 "automatically created in the model when "
                                 "LITP is started.",
                validators=[MSValidator()],
                hostname=Property(
                    "hostname",
                    prop_description="hostname for this node.",
                    required=True,
                    default=socket.gethostname(),
                    site_specific=True
                ),
                domain=Property(
                    "domain",
                    prop_description="domain for this node.",
                    site_specific=True
                ),
                ilo_ipaddress=Property(
                    "ipv4_address",
                    required=False,
                    site_specific=True,
                    prop_description="IPv4 address for the ilo interface.",
                    configuration=False
                ),
                file_systems=RefCollection(
                    "file-system-base", require="storage_profile"
                ),
                managed_files=RefCollection("managed-file-base"
                ),
                os=Reference("os-profile", require="system"),
                system=Reference("system"),
                routes=RefCollection("route-base",
                                     require="network_interfaces"),
                network_interfaces=Collection(
                    "network-interface",
                    require="os",
                    min_count=0,
                ),
                items=RefCollection("software-item",
                                    require="file_systems"),
                storage_profile=Reference("storage-profile-base",
                                          require="routes"),
                services=Collection(
                    "service-base",
                    require="file_systems"),
                libvirt=Reference("system-provider", require="services"),
                configs=Collection("node-config",
                                   require="file_systems"),
            ),
            ItemType(
                "infrastructure",
                item_description="This item type is a child of root and an "
                                 "item of this type is automatically created "
                                 "in the model when LITP is started. It "
                                 "contains deployment model items which "
                                 "describe configuration information intended "
                                 "to be shared across several peer servers.",
                items=Collection("infra-item"),
                systems=Collection("system"),
                system_providers=Collection("system-provider"),
                service_providers=Collection("service-provider"),
                networking=Child("networking", required=True),
                storage=Child("storage", required=True)
            ),
            ItemType(
                "networking",
                item_description="This single-instance item type is the type "
                                 "of the only item in "
                                 "/infrastructure/networking. "
                                 "It represents a container for networking "
                                 "configuration items.",
                networks=Collection("network"),
                routes=Collection("route-base"),
            ),
            ItemType(
                "network",
                item_description="This item type represents an"
                                 " Ethernet broadcast domain shared"
                                 " by peer server interfaces.",
                name=Property("basic_string",
                    prop_description="Name used for soft-linking to this "
                        "network.",
                    required=True),
                subnet=Property("network",
                    prop_description="IPv4 CIDR definition for this network.",
                    required=False,
                    site_specific=True),
                litp_management=Property("basic_boolean",
                    prop_description="Use this network for installation and "
                        "management.",
                    default='false',
                    required=True,
                    updatable_rest=False)
            ),
            ItemType(
                "route-base",
                item_description="This is the base item type"
                                 " for non-local IP routes." + \
                                 CoreExtension.base_type_description,
            ),
            ItemType(
                "service-provider",
                item_description="This is the base item type for a service "
                                 "(application resource) provider.",
            ),
            ItemType(
                "system-provider",
                item_description="Base system-provider item type." + \
                                 CoreExtension.base_type_description,
            ),
            ItemType(
                "infra-item",
                item_description="This is the base item type for an "
                                 "infrastructure item." + \
                                 CoreExtension.base_type_description,
            ),
            ItemType(
                "task",
                item_description="This item type represents a task within the "
                                 "LITP plan. Tasks are generated when a plan "
                                 "is created and they cannot be modified or "
                                 "deleted.",
            ),
            ItemType(
                "phase",
                item_description="This item type represents a phase in the "
                                 "LITP plan. Phases group together a set of "
                                 "plan tasks that can be executed "
                                 "simultaneously.",
                tasks=Collection("task", min_count=1),
            ),
            ItemType(
                "plan",
                item_description="This item type is a child of root and is "
                                 "automatically created in the model when "
                                 "LITP is started. It contains plan "
                                 "information.",
                state=Property(
                    "plan_state",
                    prop_description="State of the plan.",
                    updatable_rest=False,
                    updatable_plugin=False,
                ),
                phases=Collection("phase", min_count=1),
            ),
            ItemType(
                "litp-service-base",
                item_description="This is the base item type for internal "
                                 "LITP services configuration endpoints."
            ),
            ItemType(
                "logging",
                item_description=(
                    "The service that can be updated to force debug logging."
                ),
                force_debug=Property(
                    "basic_boolean",
                    prop_description="Force trace logging",
                    default="false",
                    required=True
                ),
                force_postgres_debug=Property(
                    "basic_boolean",
                    prop_description="Log postgres connections",
                    default="false",
                    required=True
                ),
                extend_item="litp-service-base"
            ),
            ItemType(
                "restore",
                item_description="Restore LITP model to last applied state",
                update_trigger=Property("basic_string",
                    prop_description="Update this property to any non-empty "
                        "string to trigger a model restore",
                    default="updatable",
                    required=True
                ),
                extend_item="litp-service-base"
            ),
            ItemType(
                "import-iso",
                item_description="Import packages and images from a "
                                 "LITP-compliant ISO.",
                source_path=Property(
                    "path_string_incl_root",
                    prop_description="Path where the ISO is mounted.",
                    default="/",
                    required=True,
                ),
                extend_item="litp-service-base"
            ),
            ItemType(
                "maintenance",
                item_description="Handles LITP's maintenance mode",
                enabled=Property(
                   "basic_boolean",
                   prop_description="Put LITP in maintenance mode",
                   default="false",
                   required=True
                ),
                status=Property(
                    "any_string",
                    prop_description="Status of the background job",
                    required=False,
                    default="None",
                    updatable_plugin=False,
                    updatable_rest=False,
                ),
                initiator=Property(
                   "any_string",
                   prop_description="Store the initiator of maintenance mode",
                   default="",
                   required=False,
                   updatable_plugin=True,
                   updatable_rest=False
                ),
                extend_item="litp-service-base"
            ),
            ItemType(
                "sshd-config",
                extend_item="node-config",
                item_description="Configs for SSH Daemon",
                permit_root_login=Property(
                    "basic_boolean",
                    prop_description="Permit or prevent root login",
                    default="true",
                    updatable_rest=True,
                    updatable_plugin=False,
                )
            ),
            ItemType(
                "upgrade",
                item_description=("This item type represents an "
                                "RPM (Red Hat Package Manager) "
                                "upgrade in the node to which "
                                "it belongs. When a plan is "
                                "created, Yum queries the "
                                "repositories to determine "
                                "whether any package requires update."),
                hash=Property(
                    "basic_string",
                    prop_description="Unique id to identify an upgrade. Will "
                    "be generated by LITP.",
                    required=False,
                    updatable_plugin=True,
                    updatable_rest=False
                ),
                requires_reboot=Property(
                    "basic_boolean",
                    prop_description="Whether the upgrade requires a "
                    "node reboot. Will be generated by LITP.",
                    required=False,
                    updatable_plugin=True,
                    updatable_rest=False
                ),
                reboot_performed=Property(
                    "basic_boolean",
                    prop_description="Whether the reboot task has been done."
                    " Will be generated by LITP.",
                    required=False,
                    updatable_plugin=True,
                    updatable_rest=False
                ),
                disable_reboot=Property(
                    "basic_boolean",
                    prop_description="Disable the LITP generated reboot.",
                    required=False,
                    configuration=False
                ),
                os_reinstall=Property(
                    "basic_boolean",
                    prop_description="OS re-install.",
                    required=False,
                    configuration=False
                ),
                ha_manager_only=Property(
                    "basic_boolean",
                    prop_description="Confine task generation to upgrade" +
                     " the HA Manager only.",
                    required=False,
                    configuration=False
                ),
                redeploy_ms=Property(
                    "basic_boolean",
                    prop_description="Redeploy MS.",
                    required=False,
                    configuration=False
                ),
                infra_update=Property(
                    "basic_boolean",
                    prop_description="Infrastructure update.",
                    required=False,
                    configuration=False
                ),
                pre_os_reinstall=Property(
                    "basic_boolean",
                    prop_description="Pre OS re-install.",
                    required=False,
                    configuration=False
                )
            ),
            ItemType("image-base",
                item_description="This is the base item type for an image." + \
                                 CoreExtension.base_type_description,
            ),
            ItemType(
                "prepare-restore",
                item_description="Prepares LITP to restore to initial",
                path=Property(
                    "path_string_incl_root",
                    prop_description="Path to restore",
                    default='/'
                ),
                actions=Property(
                    "prepare_actions",
                    prop_description="Actions for restore",
                    default='all'
                ),
                force_remove_snapshot=Property(
                    "basic_boolean",
                    prop_description="Force remove snapshot for restore",
                    required=False,
                    default='false'
                ),
                extend_item="litp-service-base"
            )
        ]

    @staticmethod
    def resolve_clustered_service_nodes(plugin_api_context, clustered_service):
        cluster = CoreExtension._parent_cluster(plugin_api_context,
                                                clustered_service)
        if not cluster:
            raise ViewError()
        node_list = clustered_service.node_list.split(',')
        node_dict = dict((node.item_id, node) for node in cluster.nodes)
        return [node_dict[node_id]
                for node_id in node_list if node_id in node_dict]

    @staticmethod
    def resolve_clustered_service_dependencies(plugin_api_context,
                                               clustered_service):
        cluster = CoreExtension._parent_cluster(plugin_api_context,
                                                clustered_service)
        if not cluster:
            raise ViewError()
        dependencies = []
        if clustered_service.dependency_list:
            dependency_list = clustered_service.dependency_list.split(',')
            for service in cluster.services:
                if service.item_id in dependency_list:
                    dependencies.append(service)
        return dependencies

    @staticmethod
    def _parent_cluster(plugin_api_context, qitem):
        while True:
            if qitem.get_vpath() == '/':
                return None
            if qitem.is_cluster():
                return qitem
            qparent_path = '/'.join(qitem.get_vpath().split('/')[:-1])
            qitem = plugin_api_context.query_by_vpath(qparent_path)

    @staticmethod
    def gen_disk_fact_name(plugin_api_context, disk_item):
        """
        Returns a fact name for a specific disk, based on its UUID and
        whether its parent VG is a root VG or not. This return value will be
        used to get the physical device name.
        :param plugin_api_context: plugin api context instance.
        :type  pulgin_api_context: PluginApiContext
        :param disk_item: disk for which we want to get the fact name.
        :type  disk_item: ModelItem
        """
        disk_fact_name = ''
        is_root_vg = False
        disk_node = disk_item.get_node()
        if disk_node:
            devices = disk_node.storage_profile.query(
                                  "physical-device", device_name=disk_item.name
                                                     )
            if devices:
                # TODO: parent.parent is ugly
                volume_group_name = devices[0].parent.parent.volume_group_name
            else:
                raise ViewError("No physical device found with device_name "\
                                "\"{0}\"".format(disk_item.name))
            root_vg_name = disk_node.storage_profile.view_root_vg
            if root_vg_name and (volume_group_name == root_vg_name):
                is_root_vg = True
            if disk_item.uuid:
                disk_fact_name = '$::disk_' + \
                                 disk_item.uuid.lower().replace('-', '_')
            if is_root_vg == True:
                if disk_item.bootable == 'true':
                    disk_fact_name += '_part3'
                else:
                    if hasattr(disk_item, "disk_part") and\
                                            disk_item.disk_part == 'true':
                        disk_fact_name += '_part1'
            disk_fact_name += '_dev'
        return disk_fact_name

    @staticmethod
    def _validate_cluster_dependency_list(cluster, dependencies):
        errors = []
        if cluster.item_id in dependencies:
            error_message = ('A cluster cannot depend on itself. Please '
                             'ensure "dependency_list" property is correct '
                             'for cluster "%s".' % cluster.item_id)
            errors.append(error_message)

        duplicates = set(item_id for item_id in dependencies if
                      dependencies.count(item_id) > 1)
        if duplicates:
            error_message = ('Only one occurrence of a cluster is allowed '
                             'in "dependency_list" property. The following '
                             'clusters are repeated: {0}.').format(
                                     ', '.join(duplicates))
            errors.append(error_message)

        return errors

    @staticmethod
    def get_ordered_clusters(plugin_api_context, deployment):
        cluster_dependency_graph = {}
        all_clusters = set()
        errors = []

        for cluster in deployment.query("cluster-base"):
            cluster_dep_list = cluster.properties.get("dependency_list")
            all_clusters.add(cluster.item_id)

            if not cluster_dep_list:
                continue

            dependencies = [token.strip()
                    for token in cluster_dep_list.split(",")]

            errors.extend(CoreExtension._validate_cluster_dependency_list(
                                                                 cluster,
                                                                 dependencies))

            cluster_dependency_graph[cluster.item_id] = set(dependencies)

        ordered_cluster_ids = []
        try:
            for indep_clusters in topsort(cluster_dependency_graph):
                ordered_cluster_ids.extend(sorted(indep_clusters))
        except CyclicGraphException as ex:
            errors.append("%s." % str(ex))

        unordered_clusters = all_clusters - set(ordered_cluster_ids)
        ordered_cluster_ids.extend(sorted(list(unordered_clusters)))

        ordered_clusters_qi = []
        for cluster_id in ordered_cluster_ids:
            try:
                ordered_clusters_qi.append(
                    deployment.query("cluster-base", item_id=cluster_id)[0])
            except IndexError:
                errors.append("Unknown cluster with id='%s' specified in "
                              "cluster dependency_list." % (cluster_id))

        if errors:
            raise ViewError(" ".join(errors))

        return ordered_clusters_qi


class MSValidator(ItemValidator):
    """
    Custom ItemValidator for MS item type.

    Ensures the value of MS hostname in the model match the actual hostname
    of the box running LITP.
    """
    def validate(self, properties):
        hostname = properties.get("hostname")
        if hostname != self.get_hostname():
            return ValidationError(
                    property_name="hostname",
                    error_message=("The value must match the current " +
                        "hostname of the Management Server"))

    def get_hostname(self):
        return socket.gethostname()
