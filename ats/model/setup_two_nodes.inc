litp create -p /infrastructure/systems/sys1 -t system -o system_name="sys1"
litp create -p /infrastructure/systems/sys2 -t system -o system_name="sys2"
litp create -p /infrastructure/networking/networks/mgmt_iprange2 -t network -o name="mgmt" subnet="10.10.10.0/24"
litp create -p /infrastructure/storage/storage_profiles/profile_1 -t storage-profile-base

litp create -p /software/profiles/osprofile1 -t os-profile -o name="node-iso-x86_64" version="rhel6" arch="x86_64" breed="linux" path="/cobbler/ks_mirror/node-iso-x86_64"

litp create -p /deployments/site1 -t deployment
litp create -p /deployments/site1/clusters/cluster1 -t cluster
litp create -p /deployments/site1/clusters/cluster1/nodes/node1 -t node -o hostname="node1"
litp create -p /deployments/site1/clusters/cluster1/nodes/node2 -t node -o hostname="node2"

litp inherit -p /deployments/site1/clusters/cluster1/nodes/node1/system -s /infrastructure/systems/sys1
litp inherit -p /deployments/site1/clusters/cluster1/nodes/node2/system -s /infrastructure/systems/sys2

litp inherit -p /deployments/site1/clusters/cluster1/nodes/node1/os -s /software/profiles/osprofile1
litp inherit -p /deployments/site1/clusters/cluster1/nodes/node2/os -s /software/profiles/osprofile1

litp create -p /deployments/site1/clusters/cluster1/nodes/node1/network_interfaces/ip1 -t network-interface -o network_name="mgmt"
litp create -p /deployments/site1/clusters/cluster1/nodes/node2/network_interfaces/ip1 -t network-interface -o network_name="mgmt"

litp inherit -p /deployments/site1/clusters/cluster1/nodes/node1/storage_profile -s /infrastructure/storage/storage_profiles/profile_1

litp inherit -p /deployments/site1/clusters/cluster1/nodes/node2/storage_profile -s /infrastructure/storage/storage_profiles/profile_1
