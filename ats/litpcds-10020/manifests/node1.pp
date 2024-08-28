
class task_node1__package__telnet(){
    package { "telnet":
        ensure => "installed"
    }
}


node "node1" {

    class {'litp::mn_node':
        ms_hostname => "ms1",
        cluster_type => "NON-CMW"
        }


    class {'task_node1__package__telnet':
    }


}