# Remove previous items and create source and reference items with
# overwritten property for next test case
litp remove -p /deployments/local/clusters/cluster1/nodes/node1/items/prop2_new_repo
litp remove -p /software/items/prop2_new_repo

# create_plan without invoking plugin update model
litp update -p /software/items/foo -o name='anything'
litp create_plan
litp run_plan
assertPlanState successful
assertNone -p /software/items/prop2_new_repo
assertNone -p /deployments/local/clusters/cluster1/nodes/node1/items/prop2_new_repo

# Create reference item with overwritten property
litp create -p /software/items/prop2_new_repo -t myrepository -o name='prop2_new_repo' myprop1='orig'
litp inherit -p /deployments/local/clusters/cluster1/nodes/node1/items/prop2_new_repo -s /software/items/prop2_new_repo -o myprop2='local'

litp create_plan
litp run_plan
assertPlanState successful



