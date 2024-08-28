class task_ms1__cobblerdata_3a_3aimport__distro__foo(){
    cobblerdata::import_distro { "foo":

    }
}


node "ms1" {

    class {'litp::ms_node':}


    class {'task_ms1__cobblerdata_3a_3aimport__distro__foo':
    }


}
