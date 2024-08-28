litp create -p /infrastructure/storage/storage_profiles/profile_1 -t storage-profile-base

litp inherit -p /deployments/site1/clusters/cluster1/nodes/node1/storage_profile -s /infrastructure/storage/storage_profiles/profile_1

litp inherit -p /deployments/site1/clusters/cluster1/nodes/node2/storage_profile -s /infrastructure/storage/storage_profiles/profile_1
