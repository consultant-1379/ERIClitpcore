class task_node1__file__item1__file(){
    file { "item1_file":
        configure => "for_removal"
    }
}

class task_node1__notify___2fdeployments_2flocal_2fclusters_2fcluster1_2fnodes_2fnode1_2fitems_2fitem2(){
    notify { "/deployments/local/clusters/cluster1/nodes/node1/items/item2":

    }
}

class task_node1__package__item1__package(){
    package { "item1_package":
        configure => "for_removal"
    }
}


node "node1" {

    class {'litp::mn_node':
        ms_hostname => "ms1",
        cluster_type => "NON-CMW"
        }


    class {'task_node1__file__item1__file':
    }


    class {'task_node1__notify___2fdeployments_2flocal_2fclusters_2fcluster1_2fnodes_2fnode1_2fitems_2fitem2':
    }


    class {'task_node1__package__item1__package':
    }


}