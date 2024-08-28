
class task_ms1__package__telnet(){
    package { "telnet":
        ensure => "installed"
    }
}


node "ms1" {

    class {'litp::ms_node':}


    class {'task_ms1__package__telnet':
    }


}