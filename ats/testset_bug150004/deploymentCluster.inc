runLitpScript minimum_deployment.inc

# Cluster 2
litp create -p /deployments/d1/clusters/c2 -t cluster

litp create -p /infrastructure/systems/sys3 -t system -o system_name=MN2
litp create -p /infrastructure/systems/sys3/disks/disk0 -t disk -o name=hd0 size=40G bootable=true uuid=at
litp create -p /deployments/d1/clusters/c2/nodes/n1 -t node -o hostname=node1-c2
litp inherit -p /deployments/d1/clusters/c2/nodes/n1/system -s /infrastructure/systems/sys3
litp inherit -p /deployments/d1/clusters/c2/nodes/n1/os -s /software/profiles/rhel_6_4
litp inherit -p /deployments/d1/clusters/c2/nodes/n1/storage_profile -s /infrastructure/storage/storage_profiles/profile_1
litp create -p /deployments/d1/clusters/c2/nodes/n1/network_interfaces/if0 -t network-interface


# Cluster 3
litp create -p /deployments/d1/clusters/c3 -t cluster

litp create -p /infrastructure/systems/sys4 -t system -o system_name=MN2
litp create -p /infrastructure/systems/sys4/disks/disk0 -t disk -o name=hd0 size=40G bootable=true uuid=at2
litp create -p /deployments/d1/clusters/c3/nodes/n1 -t node -o hostname=node1-c3
litp inherit -p /deployments/d1/clusters/c3/nodes/n1/system -s /infrastructure/systems/sys4
litp inherit -p /deployments/d1/clusters/c3/nodes/n1/os -s /software/profiles/rhel_6_4
litp inherit -p /deployments/d1/clusters/c3/nodes/n1/storage_profile -s /infrastructure/storage/storage_profiles/profile_1
litp create -p /deployments/d1/clusters/c3/nodes/n1/network_interfaces/if0 -t network-interface


litp create_plan
litp run_plan


