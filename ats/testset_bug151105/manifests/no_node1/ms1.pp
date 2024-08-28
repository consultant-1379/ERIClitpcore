
class task_ms1__package__nano(){
    package { "nano":
        ensure => "installed"
    }
}


node "ms1" {

    class {'litp::ms_node':}


    class {'task_ms1__package__nano':
    }


}