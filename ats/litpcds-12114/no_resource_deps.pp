class task_node1__package__httpd(){
    package { "httpd":
        ensure => "absent"
    }
}

class task_node1__package__httpd_2dtools(){
    package { "httpd-tools":
        ensure => "absent"
    }
}


node "node1" {

    class {'litp::mn_node':
        ms_hostname => "ms1",
        cluster_type => "NON-CMW"
        }


    class {'task_node1__package__httpd':
    }


    class {'task_node1__package__httpd_2dtools':
    }


}
