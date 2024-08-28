class task_node1__foo4__bar4(){
    foo4 { "bar4":
        name => "tc01_foobar2"
    }
}

class task_node1__foo5__bar5(){
    foo5 { "bar5":
        name => "tc01_foobar3"
    }
}


node "node1" {

    class {'litp::mn_node':
        ms_hostname => "ms1",
        cluster_type => "NON-CMW"
        }


    class {'task_node1__foo4__bar4':
    }


    class {'task_node1__foo5__bar5':
    }


}
