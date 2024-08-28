class task_node1__file__apache_2econf(){
    file { "apache.conf":
        ensure => "present"
    }
}

class task_node1__file__httpd_2econf(){
    file { "httpd.conf":
        ensure => "present"
    }
}

class task_node1__package__package__1(){
    package { "package_1":
        ensure => "present"
    }
}

class task_node1__package__package__2(){
    package { "package_2":
        ensure => "present"
    }
}

class task_node1__service__apache(){
    service { "apache":
        ensure => "present"
    }
}


node "node1" {

    class {'litp::mn_node':
        ms_hostname => "ms1",
        cluster_type => "NON-CMW"
        }


    class {'task_node1__file__apache_2econf':
    }


    class {'task_node1__file__httpd_2econf':
    }


    class {'task_node1__package__package__1':
    }


    class {'task_node1__package__package__2':
    }


    class {'task_node1__service__apache':
    }


}

