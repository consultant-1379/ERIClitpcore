class task_node1__foo1__bar1(){
    foo1 { "bar1":
        name => "tc11_foobar1"
    }
}


node "node1" {

    class {'litp::mn_node':
        ms_hostname => "ms1",
        cluster_type => "NON-CMW"
        }


    class {'task_node1__foo1__bar1':
    }


}
