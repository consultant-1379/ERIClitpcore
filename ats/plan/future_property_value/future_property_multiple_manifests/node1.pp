
class task_node1__package__test__item(){
    package { "test_item":
        version => "Y.Y.Y"
    }
}

class task_node1__package__test__item__another(){
    package { "test_item_another":
        version => "Z.Z.Z"
    }
}


node "node1" {

    class {'litp::mn_node':
        ms_hostname => "ms1",
        cluster_type => "NON-CMW"
        }


    class {'task_node1__package__test__item':
    }


    class {'task_node1__package__test__item__another':
        require => [Class["task_node1__package__test__item"]]
    }


}