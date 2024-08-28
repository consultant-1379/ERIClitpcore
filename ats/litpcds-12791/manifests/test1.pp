class task_ms1__eth__test1(){
    eth { "test1":
        ensure => "present"
    }
}

class task_ms1__package__test1(){
    package { "test1":

    }
}

class task_ms1__service__test1(){
    service { "test1":

    }
}


node "ms1" {

    class {'litp::ms_node':}


    class {'task_ms1__eth__test1':
        require => [Class["task_ms1__package__test1"]]
    }


    class {'task_ms1__package__test1':
    }


    class {'task_ms1__service__test1':
        require => [Class["task_ms1__eth__test1"]]
    }


}

