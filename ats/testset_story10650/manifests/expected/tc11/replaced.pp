class task_node1__foo_58__bar_59(){
    fooX { "barY":
        name => "tc11_foobar2"
    }
}


node "node1" {

    class {'litp::mn_node':
        ms_hostname => "ms1",
        cluster_type => "NON-CMW"
        }


    class {'task_node1__foo_58__bar_59':
    }


}
