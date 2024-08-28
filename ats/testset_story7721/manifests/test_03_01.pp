class task_ms1__eth__test3(){
    eth { "test3":
        ensure => "absent"
    }
}

class task_ms1__service__test3(){
    service { "test3":

    }
}


node "ms1" {

    class {'litp::ms_node':}


    class {'task_ms1__eth__test3':
    }


    class {'task_ms1__service__test3':
    }


}
