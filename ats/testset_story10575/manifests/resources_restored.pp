class task_node1__file__item2__file(){
    file { "item2_file":
        configure => "initial"
    }
}

class task_node1__package__item2__package(){
    package { "item2_package":
        configure => "initial"
    }
}


node "node1" {

    class {'litp::mn_node':
        ms_hostname => "ms1",
        cluster_type => "NON-CMW"
        }


    class {'task_node1__file__item2__file':
    }


    class {'task_node1__package__item2__package':
    }


}