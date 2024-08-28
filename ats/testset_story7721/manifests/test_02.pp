class task_ms1__service__test1(){
    service { "test1":

    }
}


node "ms1" {

    class {'litp::ms_node':}


    class {'task_ms1__service__test1':
    }


}