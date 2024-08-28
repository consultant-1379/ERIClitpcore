litp create -p /infrastructure/storage/storage_profiles/profile_1 -t storage-profile-base -o storage_profile_name=sp1

litp link -p /deployments/site1/clusters/cluster1/nodes/node1/storage_profile -t storage-profile-base -o storage_profile_name='sp1'

litp link -p /deployments/site1/clusters/cluster1/nodes/node2/storage_profile -t storage-profile-base -o storage_profile_name='sp1'

litp link -p /deployments/site1/clusters/cluster1/nodes/node3/storage_profile -t storage-profile-base -o storage_profile_name='sp1'

litp link -p /deployments/site1/clusters/cluster1/nodes/node4/storage_profile -t storage-profile-base -o storage_profile_name='sp1'
