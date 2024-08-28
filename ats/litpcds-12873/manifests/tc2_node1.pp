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


node "node1" {

    class {'litp::mn_node':
        ms_hostname => "ms1",
        cluster_type => "NON-CMW"
        }


    class {'task_node1__node_3a_3aconfigs__id__node__config':
        require => [Class["task_node1__node_3a_3afile__systems__id__node__file"]]
    }


    class {'task_node1__node_3a_3afile__systems__id__node__file':
    }


    class {'task_node1__node_3a_3aitems__id__node__item':
        require => [Class["task_node1__node_3a_3aconfigs__id__node__config"]]
    }


}
