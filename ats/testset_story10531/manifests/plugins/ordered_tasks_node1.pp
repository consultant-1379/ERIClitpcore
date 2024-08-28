class task_node1__res__1__node__res__1__node__title(){
    res_1_node { "res_1_node_title":

    }
}

class task_node1__res__2__node__res__2__node__title(){
    res_2_node { "res_2_node_title":

    }
}

class task_node1__res__3__node__res__3__node__title(){
    res_3_node { "res_3_node_title":

    }
}


node "node1" {

    class {'litp::mn_node':
        ms_hostname => "ms1",
        cluster_type => "NON-CMW"
        }


    class {'task_node1__res__1__node__res__1__node__title':
    }


    class {'task_node1__res__2__node__res__2__node__title':
        require => [Class["task_node1__res__1__node__res__1__node__title"]]
    }


    class {'task_node1__res__3__node__res__3__node__title':
        require => [Class["task_node1__res__2__node__res__2__node__title"]]
    }


}