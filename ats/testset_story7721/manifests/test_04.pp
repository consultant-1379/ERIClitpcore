class task_ms1__eth__test4(){
    eth { "test4":
        ensure => "present"
    }
}

class task_ms1__package__test4(){
    package { "test4":

    }
}

class task_ms1__service__test4(){
    service { "test4":

    }
}


node "ms1" {

    class {'litp::ms_node':}


    class {'task_ms1__eth__test4':
        require => [Class["task_ms1__package__test4"]]
    }


    class {'task_ms1__package__test4':
    }


    class {'task_ms1__service__test4':
        require => [Class["task_ms1__eth__test4"]]
    }


}