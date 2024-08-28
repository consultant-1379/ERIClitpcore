class task_ms1__item__foo(){
    item { "foo":
        drop_all => "true",
        ensure => "present",
        name => "foo"
    }
}


node "ms1" {

    class {'litp::ms_node':}


    class {'task_ms1__item__foo':
    }


}