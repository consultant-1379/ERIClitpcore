class task_ms1__eth__test5(){
    eth { "test5":

    }
}

class task_ms1__package__test5(){
    package { "test5":

    }
}

class task_ms1__service__test5(){
    service { "test5":

    }
}


node "ms1" {

    class {'litp::ms_node':}


    class {'task_ms1__eth__test5':
    }


    class {'task_ms1__package__test5':
        require => [Class["task_ms1__eth__test5"]]
    }


    class {'task_ms1__service__test5':
        require => [Class["task_ms1__eth__test5"]]
    }


}