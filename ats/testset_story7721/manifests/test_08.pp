class task_ms1__eth__dependent__test8(){
    eth_dependent { "test8":

    }
}

class task_ms1__eth__test8(){
    eth { "test8":

    }
}


node "ms1" {

    class {'litp::ms_node':}


    class {'task_ms1__eth__dependent__test8':
        require => [Class["task_ms1__eth__test8"]]
    }


    class {'task_ms1__eth__test8':
    }


}