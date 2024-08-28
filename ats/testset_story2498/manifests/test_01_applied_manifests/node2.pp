
class task_node2__package__finger(){
    package { "finger":
        ensure => "installed"
    }
}


node "node2" {

    class {'litp::mn_node':
        ms_hostname => "ms1",
        cluster_type => "NON-CMW"
        }


    class {'task_node2__package__finger':
    }


}