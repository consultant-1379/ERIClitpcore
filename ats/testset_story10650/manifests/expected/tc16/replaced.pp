class task_node1__baz1__qux1(){
    baz1 { "qux1":
        name => "tc16_depend"
    }
}

class task_node1__foo5__bar5(){
    foo5 { "bar5":
        name => "tc16_foobar2"
    }
}

class task_node1__foo6__bar6(){
    foo6 { "bar6":
        name => "tc16_foobar2"
    }
}


node "node1" {

    class {'litp::mn_node':
        ms_hostname => "ms1",
        cluster_type => "NON-CMW"
        }


    class {'task_node1__baz1__qux1':
    }


    class {'task_node1__foo5__bar5':
        require => [Class["task_node1__baz1__qux1"]]
    }


    class {'task_node1__foo6__bar6':
    }


}
