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

# Cluster_1 nodes
litp create -p /deployments/litpcds_9863/clusters/cluster_1/nodes/node1 -t node -o hostname=c1-node1
litp create -p /deployments/litpcds_9863/clusters/cluster_1/nodes/node1/network_interfaces/ip1 -t network-interface -o network_name=sample-ip-range
litp inherit -p /deployments/litpcds_9863/clusters/cluster_1/nodes/node1/os -s /software/profiles/os-profile1
litp inherit -p /deployments/litpcds_9863/clusters/cluster_1/nodes/node1/storage_profile -s /infrastructure/storage/storage_profiles/storage-profile1
litp inherit -p /deployments/litpcds_9863/clusters/cluster_1/nodes/node1/system -s /infrastructure/systems/system1

litp create -p /deployments/litpcds_9863/clusters/cluster_1/nodes/node2 -t node -o hostname=c1-node2
litp create -p /deployments/litpcds_9863/clusters/cluster_1/nodes/node2/network_interfaces/ip1 -t network-interface -o network_name=sample-ip-range
litp inherit -p /deployments/litpcds_9863/clusters/cluster_1/nodes/node2/os -s /software/profiles/os-profile1
litp inherit -p /deployments/litpcds_9863/clusters/cluster_1/nodes/node2/storage_profile -s /infrastructure/storage/storage_profiles/storage-profile1
litp inherit -p /deployments/litpcds_9863/clusters/cluster_1/nodes/node2/system -s /infrastructure/systems/system2

litp create -p /deployments/litpcds_9863/clusters/cluster_1/nodes/node3 -t node -o hostname=c1-node3
litp create -p /deployments/litpcds_9863/clusters/cluster_1/nodes/node3/network_interfaces/ip1 -t network-interface -o network_name=sample-ip-range
litp inherit -p /deployments/litpcds_9863/clusters/cluster_1/nodes/node3/os -s /software/profiles/os-profile1
litp inherit -p /deployments/litpcds_9863/clusters/cluster_1/nodes/node3/storage_profile -s /infrastructure/storage/storage_profiles/storage-profile1
litp inherit -p /deployments/litpcds_9863/clusters/cluster_1/nodes/node3/system -s /infrastructure/systems/system3

#Cluster_2 nodes
litp create -p /deployments/litpcds_9863/clusters/cluster_2/nodes/node1 -t node -o hostname=c2-node1
litp create -p /deployments/litpcds_9863/clusters/cluster_2/nodes/node1/network_interfaces/ip1 -t network-interface -o network_name=sample-ip-range
litp inherit -p /deployments/litpcds_9863/clusters/cluster_2/nodes/node1/os -s /software/profiles/os-profile1
litp inherit -p /deployments/litpcds_9863/clusters/cluster_2/nodes/node1/storage_profile -s /infrastructure/storage/storage_profiles/storage-profile1
litp inherit -p /deployments/litpcds_9863/clusters/cluster_2/nodes/node1/system -s /infrastructure/systems/system1

litp create -p /deployments/litpcds_9863/clusters/cluster_2/nodes/node2 -t node -o hostname=c2-node2
litp create -p /deployments/litpcds_9863/clusters/cluster_2/nodes/node2/network_interfaces/ip1 -t network-interface -o network_name=sample-ip-range
litp inherit -p /deployments/litpcds_9863/clusters/cluster_2/nodes/node2/os -s /software/profiles/os-profile1
litp inherit -p /deployments/litpcds_9863/clusters/cluster_2/nodes/node2/storage_profile -s /infrastructure/storage/storage_profiles/storage-profile1
litp inherit -p /deployments/litpcds_9863/clusters/cluster_2/nodes/node2/system -s /infrastructure/systems/system2

litp create -p /deployments/litpcds_9863/clusters/cluster_2/nodes/node3 -t node -o hostname=c2-node3
litp create -p /deployments/litpcds_9863/clusters/cluster_2/nodes/node3/network_interfaces/ip1 -t network-interface -o network_name=sample-ip-range
litp inherit -p /deployments/litpcds_9863/clusters/cluster_2/nodes/node3/os -s /software/profiles/os-profile1
litp inherit -p /deployments/litpcds_9863/clusters/cluster_2/nodes/node3/storage_profile -s /infrastructure/storage/storage_profiles/storage-profile1
litp inherit -p /deployments/litpcds_9863/clusters/cluster_2/nodes/node3/system -s /infrastructure/systems/system3
