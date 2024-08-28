
class task_node1__package__bar(){
    package { "bar":

    }
}

class task_node1__package__bar2(){
    package { "bar2":

    }
}

class task_node1__package__bar3(){
    package { "bar3":

    }
}

class task_node1__package__bar4(){
    package { "bar4":

    }
}

class task_node1__package__foo(){
    package { "foo":

    }
}

class task_node1__package__foo2(){
    package { "foo2":

    }
}

class task_node1__package__foo3(){
    package { "foo3":

    }
}

class task_node1__package__foo4(){
    package { "foo4":

    }
}


node "node1" {

    class {'litp::mn_node':
        ms_hostname => "ms1",
        cluster_type => "NON-CMW"
        }


    class {'task_node1__package__bar':
    }


    class {'task_node1__package__bar2':
    }


    class {'task_node1__package__bar3':
    }


    class {'task_node1__package__bar4':
    }


    class {'task_node1__package__foo':
    }


    class {'task_node1__package__foo2':
    }


    class {'task_node1__package__foo3':
    }


    class {'task_node1__package__foo4':
    }


}