
class task_node1__node__call__type__node__call__id(){
    node_call_type { "node_call_id":

    }
}

class task_node1__package__name(){
    package { "name":

    }
}


node "node1" {

    class {'litp::mn_node':
        ms_hostname => "ms1",
        cluster_type => "NON-CMW"
        }


    class {'task_node1__node__call__type__node__call__id':
    }


    class {'task_node1__package__name':
        require => [Class["task_node1__node__call__type__node__call__id"]]
    }


}