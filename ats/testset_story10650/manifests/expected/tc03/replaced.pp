class task_node1__foo3__bar3(){
    foo3 { "bar3":
        name => "tc03_foobar1"
    }
}

class task_node1__foo4__bar4(){
    foo4 { "bar4":
        name => "tc03_foobar2"
    }
}

class task_node1__foo5__bar5(){
    foo5 { "bar5":
        name => "tc03_foobar2"
    }
}


node "node1" {

    class {'litp::mn_node':
        ms_hostname => "ms1",
        cluster_type => "NON-CMW"
        }


    class {'task_node1__foo3__bar3':
        require => []
    }


    class {'task_node1__foo4__bar4':
    }


    class {'task_node1__foo5__bar5':
    }


}
