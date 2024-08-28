
class task_node1__package__file(){
    package { "file":
        ensure => "None"
    }
}

class task_node1__package__vim_2denhanced(){
    package { "vim-enhanced":
        ensure => "None"
    }
}


node "node1" {

    class {'litp::mn_node':
        ms_hostname => "ms1",
        cluster_type => "NON-CMW"
        }


    class {'task_node1__package__file':
    }


    class {'task_node1__package__vim_2denhanced':
    }


}