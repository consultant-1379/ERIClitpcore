class task_ms1__package__test6(){
    package { "test6":

    }
}

class task_ms1__service__test6(){
    service { "test6":

    }
}


node "ms1" {

    class {'litp::ms_node':}


    class {'task_ms1__package__test6':
    }


    class {'task_ms1__service__test6':
    }


}
