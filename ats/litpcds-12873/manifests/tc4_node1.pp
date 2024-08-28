class task_node1__node_3a_3aconfigs__id__node__config(){
    node::configs { "id_node_config":

    }
}

class task_node1__node_3a_3afile__systems__id__node__file(){
    node::file_systems { "id_node_file":

    }
}

class task_node1__node_3a_3aitems__id__node__item(){
    node::items { "id_node_item":

    }
}

class task_node1__node_3a_3aroutes__a__id__node__route__a(){
    node::routes_a { "id_node_route_a":

    }
}

class task_node1__node_3a_3aroutes__b__id__node__route__b(){
    node::routes_b { "id_node_route_b":

    }
}


node "node1" {

    class {'litp::mn_node':
        ms_hostname => "ms1",
        cluster_type => "NON-CMW"
        }


    class {'task_node1__node_3a_3aconfigs__id__node__config':
        require => [Class["task_node1__node_3a_3afile__systems__id__node__file"]]
    }


    class {'task_node1__node_3a_3afile__systems__id__node__file':
        require => [Class["task_node1__node_3a_3aroutes__a__id__node__route__a"],Class["task_node1__node_3a_3aroutes__b__id__node__route__b"]]
    }


    class {'task_node1__node_3a_3aitems__id__node__item':
        require => [Class["task_node1__node_3a_3aconfigs__id__node__config"]]
    }


    class {'task_node1__node_3a_3aroutes__a__id__node__route__a':
    }


    class {'task_node1__node_3a_3aroutes__b__id__node__route__b':
    }


}
