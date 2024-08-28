class task_node1__baz1__qux1(){
    baz1 { "qux1":
        name => "tc15_depend"
    }
}

class task_node1__foo1__bar1(){
    foo1 { "bar1":
        name => "tc15_foobar1"
    }
}

class task_node1__foo2__bar2(){
    foo2 { "bar2":
        name => "tc15_foobar1"
    }
}

class task_node1__foo3__bar3(){
    foo3 { "bar3":
        name => "tc15_foobar1"
    }
}

class task_node1__foo4__bar4(){
    foo4 { "bar4":
        name => "tc15_foobar1"
    }
}


node "node1" {

    class {'litp::mn_node':
        ms_hostname => "ms1",
        cluster_type => "NON-CMW"
        }


    class {'task_node1__baz1__qux1':
    }


    class {'task_node1__foo1__bar1':
        require => [Class["task_node1__baz1__qux1"]]
    }


    class {'task_node1__foo2__bar2':
        require => [Class["task_node1__foo1__bar1"]]
    }


    class {'task_node1__foo3__bar3':
        require => [Class["task_node1__foo2__bar2"]]
    }


    class {'task_node1__foo4__bar4':
        require => [Class["task_node1__foo3__bar3"]]
    }


}