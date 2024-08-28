class task_node1__baz2__qux2(){
    baz2 { "qux2":
        name => "tc05_depend2"
    }
}

class task_node1__foo1__bar1(){
    foo1 { "bar1":
        name => "tc05b_foobar1"
    }
}

class task_node1__foo3__bar3(){
    foo3 { "bar3":
        name => "tc05b_foobar1"
    }
}

class task_node1__foo5__bar5(){
    foo5 { "bar5":
        name => "tc05b_foobar2"
    }
}

class task_node1__foo6__bar6(){
    foo6 { "bar6":
        name => "tc05b_foobar2"
    }
}


node "node1" {

    class {'litp::mn_node':
        ms_hostname => "ms1",
        cluster_type => "NON-CMW"
        }


    class {'task_node1__baz2__qux2':
    }


    class {'task_node1__foo1__bar1':
        require => [Class["task_node1__baz2__qux2"]]
    }


    class {'task_node1__foo3__bar3':
        require => [Class["task_node1__baz2__qux2"],Class["task_node1__foo1__bar1"]]
    }


    class {'task_node1__foo5__bar5':
        require => [Class["task_node1__baz2__qux2"],Class["task_node1__foo1__bar1"]]
    }


    class {'task_node1__foo6__bar6':
        require => [Class["task_node1__baz2__qux2"],Class["task_node1__foo1__bar1"],Class["task_node1__foo3__bar3"]]
    }


}
