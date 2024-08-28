class task_node1__foo6__bar6(){
    foo6 { "bar6":
        name => "tc06_foobar1"
    }
}


node "node1" {

    class {'litp::mn_node':
        ms_hostname => "ms1",
        cluster_type => "NON-CMW"
        }


    class {'task_node1__foo6__bar6':
    }


}
