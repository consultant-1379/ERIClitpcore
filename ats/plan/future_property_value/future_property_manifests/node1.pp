
class task_node1__package__test__item(){
    package { "test_item":
        version => "Y.Y.Y"
    }
}


node "node1" {

    class {'litp::mn_node':
        ms_hostname => "ms1",
        cluster_type => "NON-CMW"
        }


    class {'task_node1__package__test__item':
    }


}