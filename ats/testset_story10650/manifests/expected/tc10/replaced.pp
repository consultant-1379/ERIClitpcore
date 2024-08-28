class task_node1__foo2__bar2(){
    foo2 { "bar2":
        name => "tc10_foobar1"
    }
}

class task_node1__foo3__bar3(){
    foo3 { "bar3":
        name => "tc10_foobar1"
    }
}

class task_node1__foo4__bar4(){
    foo4 { "bar4":
        name => "tc10_foobar2"
    }
}


node "node1" {

    class {'litp::mn_node':
        ms_hostname => "ms1",
        cluster_type => "NON-CMW"
        }


    class {'task_node1__foo2__bar2':
    }


    class {'task_node1__foo3__bar3':
    }


    class {'task_node1__foo4__bar4':
        require => [Class["task_node1__foo2__bar2"],Class["task_node1__foo3__bar3"]]
    }


}
