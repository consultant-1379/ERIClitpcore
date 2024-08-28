class task_ms1__eth__test6(){
    eth { "test6":

    }
}

class task_ms1__service__test6(){
    service { "test6":

    }
}

class task_ms1__system__test6(){
    system { "test6":

    }
}


node "ms1" {

    class {'litp::ms_node':}


    class {'task_ms1__eth__test6':
        require => [Class["task_ms1__system__test6"]]
    }


    class {'task_ms1__service__test6':
        require => [Class["task_ms1__eth__test6"]]
    }


    class {'task_ms1__system__test6':
    }


}