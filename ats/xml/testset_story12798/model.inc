# 1. Create source parent, child and grandchild items
litp create -p /software/services/parent1 -t parent -o name=parent1 # source item
litp create -p /software/services/parent1/childs/child1 -t child -o name=child1
litp create -p /software/services/parent1/childs/child1/grand_children/grandchild1 -t grand-child -o name=grandchild1

assertState -p /software/services/parent1 Initial
assertState -p /software/services/parent1/childs/child1 Initial
assertState -p /software/services/parent1/childs/child1/grand_children/grandchild1 Initial

# 2. inheritance: Node 1 inherits from software services
litp inherit -p /deployments/local/clusters/cluster1/nodes/node1/services/parent1 -s /software/services/parent1
assertState -p /deployments/local/clusters/cluster1/nodes/node1/services/parent1 Initial
assertState -p /deployments/local/clusters/cluster1/nodes/node1/services/parent1/childs/child1 Initial
assertState -p /deployments/local/clusters/cluster1/nodes/node1/services/parent1/childs/child1/grand_children/grandchild1 Initial

# 3. double inheritance: Node 2 inherits from Node 1
litp inherit -p /deployments/local/clusters/cluster1/nodes/node2/services/parent1 -s /deployments/local/clusters/cluster1/nodes/node1/services/parent1
assertState -p /deployments/local/clusters/cluster1/nodes/node2/services/parent1 Initial
assertState -p /deployments/local/clusters/cluster1/nodes/node2/services/parent1/childs/child1 Initial
assertState -p /deployments/local/clusters/cluster1/nodes/node2/services/parent1/childs/child1/grand_children/grandchild1 Initial

# 4. Updated double inheritance: Update Node 2 grandchild
litp update -p /deployments/local/clusters/cluster1/nodes/node2/services/parent1/childs/child1/grand_children/grandchild1  -o name=grandchild1Prime

# 5. Execute "create_plan"
litp create_plan
litp run_plan
assertPlanState successful

# 6. Assert model in state Applied and property set for node 2 grandchild
assertState -p /software/services/parent1 Applied
assertState -p /software/services/parent1/childs/child1 Applied
assertState -p /software/services/parent1/childs/child1/grand_children/grandchild1 Applied
assertState -p /deployments/local/clusters/cluster1/nodes/node1/services/parent1 Applied
assertState -p /deployments/local/clusters/cluster1/nodes/node1/services/parent1/childs/child1 Applied
assertState -p /deployments/local/clusters/cluster1/nodes/node1/services/parent1/childs/child1/grand_children/grandchild1 Applied
assertState -p /deployments/local/clusters/cluster1/nodes/node2/services/parent1 Applied
assertState -p /deployments/local/clusters/cluster1/nodes/node2/services/parent1/childs/child1 Applied
assertState -p /deployments/local/clusters/cluster1/nodes/node2/services/parent1/childs/child1/grand_children/grandchild1 Applied
assertProperty /deployments/local/clusters/cluster1/nodes/node2/services/parent1/childs/child1/grand_children/grandchild1 -o name='grandchild1Prime'
