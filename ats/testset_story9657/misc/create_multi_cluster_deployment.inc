### Create deployment items
# Infrastructure and software items
litp create -p /ms/services/cobbler -t boot-service

litp create -p /infrastructure/networking/networks/ip-range1 -t network -o name=sample-ip-range subnet=10.10.10.0/24
litp create -p /software/profiles/os-profile1 -t os-profile -o name=sample-os-profile path=/var/www/cobbler/ks_mirror/node-iso-x86_64
litp create -p /infrastructure/storage/storage_profiles/storage-profile1 -t storage-profile-base
litp create -p /infrastructure/systems/system1 -t system -o system_name=sample-system1
litp create -p /infrastructure/systems/system1/disks/disk0 -t disk -o name=hd0 size=512G bootable=true uuid="0x5000c50035ca73fe"
litp create -p /infrastructure/systems/system2 -t system -o system_name=sample-system2
litp create -p /infrastructure/systems/system2/disks/disk0 -t disk -o name=hd0 size=512G bootable=true uuid="0x5000c50035ca73fe"
litp create -p /infrastructure/systems/system3 -t system -o system_name=sample-system3
litp create -p /infrastructure/systems/system3/disks/disk0 -t disk -o name=hd0 size=512G bootable=true uuid="0x5000c50035ca73fe"
litp create -p /infrastructure/systems/system4 -t system -o system_name=sample-system4
litp create -p /infrastructure/systems/system4/disks/disk0 -t disk -o name=hd0 size=512G bootable=true uuid="0x5000c50035ca73fe"

# Deployment and clusters
litp create -p /deployments/litpcds_9657 -t deployment
litp create -p /deployments/litpcds_9657/clusters/cluster_1 -t cluster -o dependency_list='cluster_2' ha_manager="cmw"
litp create -p /deployments/litpcds_9657/clusters/cluster_2 -t cluster -o dependency_list='cluster_3' ha_manager="cmw"
litp create -p /deployments/litpcds_9657/clusters/cluster_3 -t cluster -o dependency_list='' ha_manager="cmw"
litp create -p /deployments/litpcds_9657/clusters/cluster_alpha -t cluster -o ha_manager="cmw"
litp create -p /deployments/litpcds_9657/clusters/cluster_zulu -t cluster -o ha_manager="cmw"
# This is a HA-less cluster - there won't be lock/unlock tasks for it
litp create -p /deployments/litpcds_9657/clusters/cluster_no_ha -t cluster


# Cluster_1 nodes
litp create -p /deployments/litpcds_9657/clusters/cluster_1/nodes/node1 -t node -o hostname=c1-node1
litp create -p /deployments/litpcds_9657/clusters/cluster_1/nodes/node1/network_interfaces/ip1 -t network-interface -o network_name=sample-ip-range
litp inherit -p /deployments/litpcds_9657/clusters/cluster_1/nodes/node1/os -s /software/profiles/os-profile1
litp inherit -p /deployments/litpcds_9657/clusters/cluster_1/nodes/node1/storage_profile -s /infrastructure/storage/storage_profiles/storage-profile1
litp inherit -p /deployments/litpcds_9657/clusters/cluster_1/nodes/node1/system -s /infrastructure/systems/system1

litp create -p /deployments/litpcds_9657/clusters/cluster_1/nodes/node2 -t node -o hostname=c1-node2
litp create -p /deployments/litpcds_9657/clusters/cluster_1/nodes/node2/network_interfaces/ip1 -t network-interface -o network_name=sample-ip-range
litp inherit -p /deployments/litpcds_9657/clusters/cluster_1/nodes/node2/os -s /software/profiles/os-profile1
litp inherit -p /deployments/litpcds_9657/clusters/cluster_1/nodes/node2/storage_profile -s /infrastructure/storage/storage_profiles/storage-profile1
litp inherit -p /deployments/litpcds_9657/clusters/cluster_1/nodes/node2/system -s /infrastructure/systems/system2

litp create -p /deployments/litpcds_9657/clusters/cluster_1/nodes/node3 -t node -o hostname=c1-node3
litp create -p /deployments/litpcds_9657/clusters/cluster_1/nodes/node3/network_interfaces/ip1 -t network-interface -o network_name=sample-ip-range
litp inherit -p /deployments/litpcds_9657/clusters/cluster_1/nodes/node3/os -s /software/profiles/os-profile1
litp inherit -p /deployments/litpcds_9657/clusters/cluster_1/nodes/node3/storage_profile -s /infrastructure/storage/storage_profiles/storage-profile1
litp inherit -p /deployments/litpcds_9657/clusters/cluster_1/nodes/node3/system -s /infrastructure/systems/system3

#Cluster_2 nodes
litp create -p /deployments/litpcds_9657/clusters/cluster_2/nodes/node1 -t node -o hostname=c2-node1
litp create -p /deployments/litpcds_9657/clusters/cluster_2/nodes/node1/network_interfaces/ip1 -t network-interface -o network_name=sample-ip-range
litp inherit -p /deployments/litpcds_9657/clusters/cluster_2/nodes/node1/os -s /software/profiles/os-profile1
litp inherit -p /deployments/litpcds_9657/clusters/cluster_2/nodes/node1/storage_profile -s /infrastructure/storage/storage_profiles/storage-profile1
litp inherit -p /deployments/litpcds_9657/clusters/cluster_2/nodes/node1/system -s /infrastructure/systems/system1

litp create -p /deployments/litpcds_9657/clusters/cluster_2/nodes/node2 -t node -o hostname=c2-node2
litp create -p /deployments/litpcds_9657/clusters/cluster_2/nodes/node2/network_interfaces/ip1 -t network-interface -o network_name=sample-ip-range
litp inherit -p /deployments/litpcds_9657/clusters/cluster_2/nodes/node2/os -s /software/profiles/os-profile1
litp inherit -p /deployments/litpcds_9657/clusters/cluster_2/nodes/node2/storage_profile -s /infrastructure/storage/storage_profiles/storage-profile1
litp inherit -p /deployments/litpcds_9657/clusters/cluster_2/nodes/node2/system -s /infrastructure/systems/system2

litp create -p /deployments/litpcds_9657/clusters/cluster_2/nodes/node3 -t node -o hostname=c2-node3
litp create -p /deployments/litpcds_9657/clusters/cluster_2/nodes/node3/network_interfaces/ip1 -t network-interface -o network_name=sample-ip-range
litp inherit -p /deployments/litpcds_9657/clusters/cluster_2/nodes/node3/os -s /software/profiles/os-profile1
litp inherit -p /deployments/litpcds_9657/clusters/cluster_2/nodes/node3/storage_profile -s /infrastructure/storage/storage_profiles/storage-profile1
litp inherit -p /deployments/litpcds_9657/clusters/cluster_2/nodes/node3/system -s /infrastructure/systems/system3

#Cluster_3 nodes
litp create -p /deployments/litpcds_9657/clusters/cluster_3/nodes/node1 -t node -o hostname=c3-node1
litp create -p /deployments/litpcds_9657/clusters/cluster_3/nodes/node1/network_interfaces/ip1 -t network-interface -o network_name=sample-ip-range
litp inherit -p /deployments/litpcds_9657/clusters/cluster_3/nodes/node1/os -s /software/profiles/os-profile1
litp inherit -p /deployments/litpcds_9657/clusters/cluster_3/nodes/node1/storage_profile -s /infrastructure/storage/storage_profiles/storage-profile1
litp inherit -p /deployments/litpcds_9657/clusters/cluster_3/nodes/node1/system -s /infrastructure/systems/system1

litp create -p /deployments/litpcds_9657/clusters/cluster_3/nodes/node2 -t node -o hostname=c3-node2
litp create -p /deployments/litpcds_9657/clusters/cluster_3/nodes/node2/network_interfaces/ip1 -t network-interface -o network_name=sample-ip-range
litp inherit -p /deployments/litpcds_9657/clusters/cluster_3/nodes/node2/os -s /software/profiles/os-profile1
litp inherit -p /deployments/litpcds_9657/clusters/cluster_3/nodes/node2/storage_profile -s /infrastructure/storage/storage_profiles/storage-profile1
litp inherit -p /deployments/litpcds_9657/clusters/cluster_3/nodes/node2/system -s /infrastructure/systems/system2

#Cluster_alpha nodes
litp create -p /deployments/litpcds_9657/clusters/cluster_alpha/nodes/node1 -t node -o hostname=ca-node1
litp create -p /deployments/litpcds_9657/clusters/cluster_alpha/nodes/node1/network_interfaces/ip1 -t network-interface -o network_name=sample-ip-range
litp inherit -p /deployments/litpcds_9657/clusters/cluster_alpha/nodes/node1/os -s /software/profiles/os-profile1
litp inherit -p /deployments/litpcds_9657/clusters/cluster_alpha/nodes/node1/storage_profile -s /infrastructure/storage/storage_profiles/storage-profile1
litp inherit -p /deployments/litpcds_9657/clusters/cluster_alpha/nodes/node1/system -s /infrastructure/systems/system1

litp create -p /deployments/litpcds_9657/clusters/cluster_alpha/nodes/node2 -t node -o hostname=ca-node2
litp create -p /deployments/litpcds_9657/clusters/cluster_alpha/nodes/node2/network_interfaces/ip1 -t network-interface -o network_name=sample-ip-range
litp inherit -p /deployments/litpcds_9657/clusters/cluster_alpha/nodes/node2/os -s /software/profiles/os-profile1
litp inherit -p /deployments/litpcds_9657/clusters/cluster_alpha/nodes/node2/storage_profile -s /infrastructure/storage/storage_profiles/storage-profile1
litp inherit -p /deployments/litpcds_9657/clusters/cluster_alpha/nodes/node2/system -s /infrastructure/systems/system2

#Cluster_zulu nodes
litp create -p /deployments/litpcds_9657/clusters/cluster_zulu/nodes/node1 -t node -o hostname=cz-node1
litp create -p /deployments/litpcds_9657/clusters/cluster_zulu/nodes/node1/network_interfaces/ip1 -t network-interface -o network_name=sample-ip-range
litp inherit -p /deployments/litpcds_9657/clusters/cluster_zulu/nodes/node1/os -s /software/profiles/os-profile1
litp inherit -p /deployments/litpcds_9657/clusters/cluster_zulu/nodes/node1/storage_profile -s /infrastructure/storage/storage_profiles/storage-profile1
litp inherit -p /deployments/litpcds_9657/clusters/cluster_zulu/nodes/node1/system -s /infrastructure/systems/system1

litp create -p /deployments/litpcds_9657/clusters/cluster_zulu/nodes/node2 -t node -o hostname=cz-node2
litp create -p /deployments/litpcds_9657/clusters/cluster_zulu/nodes/node2/network_interfaces/ip1 -t network-interface -o network_name=sample-ip-range
litp inherit -p /deployments/litpcds_9657/clusters/cluster_zulu/nodes/node2/os -s /software/profiles/os-profile1
litp inherit -p /deployments/litpcds_9657/clusters/cluster_zulu/nodes/node2/storage_profile -s /infrastructure/storage/storage_profiles/storage-profile1
litp inherit -p /deployments/litpcds_9657/clusters/cluster_zulu/nodes/node2/system -s /infrastructure/systems/system2

#Cluster_charlie nodes
litp create -p /deployments/litpcds_9657/clusters/cluster_no_ha/nodes/node1 -t node -o hostname=c-no-ha-node1
litp create -p /deployments/litpcds_9657/clusters/cluster_no_ha/nodes/node1/network_interfaces/ip1 -t network-interface -o network_name=sample-ip-range
litp inherit -p /deployments/litpcds_9657/clusters/cluster_no_ha/nodes/node1/os -s /software/profiles/os-profile1
litp inherit -p /deployments/litpcds_9657/clusters/cluster_no_ha/nodes/node1/storage_profile -s /infrastructure/storage/storage_profiles/storage-profile1
litp inherit -p /deployments/litpcds_9657/clusters/cluster_no_ha/nodes/node1/system -s /infrastructure/systems/system1

litp create -p /deployments/litpcds_9657/clusters/cluster_no_ha/nodes/node2 -t node -o hostname=c-no-ha-node2
litp create -p /deployments/litpcds_9657/clusters/cluster_no_ha/nodes/node2/network_interfaces/ip1 -t network-interface -o network_name=sample-ip-range
litp inherit -p /deployments/litpcds_9657/clusters/cluster_no_ha/nodes/node2/os -s /software/profiles/os-profile1
litp inherit -p /deployments/litpcds_9657/clusters/cluster_no_ha/nodes/node2/storage_profile -s /infrastructure/storage/storage_profiles/storage-profile1
litp inherit -p /deployments/litpcds_9657/clusters/cluster_no_ha/nodes/node2/system -s /infrastructure/systems/system2

# Create and inherit an item on all nodes so they can enter the Applied state
litp create -p /software/items/foo1 -t foo -o name=foo1

litp inherit -p /deployments/litpcds_9657/clusters/cluster_1/nodes/node1/items/foo1 -s /software/items/foo1
litp inherit -p /deployments/litpcds_9657/clusters/cluster_1/nodes/node2/items/foo1 -s /software/items/foo1
litp inherit -p /deployments/litpcds_9657/clusters/cluster_1/nodes/node3/items/foo1 -s /software/items/foo1

litp inherit -p /deployments/litpcds_9657/clusters/cluster_2/nodes/node1/items/foo1 -s /software/items/foo1
litp inherit -p /deployments/litpcds_9657/clusters/cluster_2/nodes/node2/items/foo1 -s /software/items/foo1

litp inherit -p /deployments/litpcds_9657/clusters/cluster_3/nodes/node1/items/foo1 -s /software/items/foo1
litp inherit -p /deployments/litpcds_9657/clusters/cluster_3/nodes/node2/items/foo1 -s /software/items/foo1

litp inherit -p /deployments/litpcds_9657/clusters/cluster_alpha/nodes/node1/items/foo1 -s /software/items/foo1
litp inherit -p /deployments/litpcds_9657/clusters/cluster_alpha/nodes/node2/items/foo1 -s /software/items/foo1

litp inherit -p /deployments/litpcds_9657/clusters/cluster_zulu/nodes/node1/items/foo1 -s /software/items/foo1
litp inherit -p /deployments/litpcds_9657/clusters/cluster_zulu/nodes/node2/items/foo1 -s /software/items/foo1

litp inherit -p /deployments/litpcds_9657/clusters/cluster_no_ha/nodes/node1/items/foo1 -s /software/items/foo1
litp inherit -p /deployments/litpcds_9657/clusters/cluster_no_ha/nodes/node2/items/foo1 -s /software/items/foo1

litp create_plan

assertState -p /deployments/litpcds_9657/clusters/cluster_1 Initial
assertState -p /deployments/litpcds_9657/clusters/cluster_2 Initial
assertState -p /deployments/litpcds_9657/clusters/cluster_3 Initial
assertState -p /deployments/litpcds_9657/clusters/cluster_alpha Initial
assertState -p /deployments/litpcds_9657/clusters/cluster_zulu Initial
assertState -p /deployments/litpcds_9657/clusters/cluster_no_ha Initial

