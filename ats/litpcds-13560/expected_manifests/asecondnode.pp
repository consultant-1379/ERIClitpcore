
class task__41_53econd_4eode__file1__a(){
    file1 { "a":

    }
}


node "ASecondNode" {

    class {'litp::mn_node':
        ms_hostname => "ms1",
        cluster_type => "NON-CMW"
        }


    class {'task__41_53econd_4eode__file1__a':
    }


}