
class task_ms1__task__t1(){
    task { "t1":
        t => "1"
    }
}


node "ms1" {

    class {'litp::ms_node':}


    class {'task_ms1__task__t1':
    }


}