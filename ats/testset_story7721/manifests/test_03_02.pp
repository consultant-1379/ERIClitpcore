class task_ms1__service__test3(){
    service { "test3":

    }
}


node "ms1" {

    class {'litp::ms_node':}


    class {'task_ms1__service__test3':
    }


}