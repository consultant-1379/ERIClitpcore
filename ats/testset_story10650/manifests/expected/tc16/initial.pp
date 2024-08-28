class task_node1__baz1__qux1(){
    baz1 { "qux1":
        name => "tc16_depend"
    }
}

class task_node1__foo1__bar1(){
    foo1 { "bar1":
        name => "tc16_foobar1"
    }
}

class task_node1__foo2__bar2(){
    foo2 { "bar2":
        name => "tc16_foobar1"
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
        require => [Class["task_node1__baz1__qux1"]]
    }


}
