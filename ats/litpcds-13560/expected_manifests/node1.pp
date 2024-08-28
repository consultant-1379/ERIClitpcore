
class task_node1__file1__a(){
    file1 { "a":

    }
}


node "node1" {

    class {'litp::mn_node':
        ms_hostname => "ms1",
        cluster_type => "NON-CMW"
        }


    class {'task_node1__file1__a':
    }


}