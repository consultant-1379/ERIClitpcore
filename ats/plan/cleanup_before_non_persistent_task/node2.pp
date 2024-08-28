
class task_node2__task__t1(){
    task { "t1":
        t => "1"
    }
}


node "node2" {

    class {'litp::mn_node':
        ms_hostname => "ms1",
        cluster_type => "NON-CMW"
        }


    class {'task_node2__task__t1':
    }


}