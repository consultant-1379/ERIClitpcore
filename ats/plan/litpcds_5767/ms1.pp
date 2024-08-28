class task_ms1__cfg_3a_3aconfig__cfg(){
    cfg::config { "cfg":

    }
}

class task_ms1__cfg_3a_3afw__fw(){
    cfg::fw { "fw":

    }
}

class task_ms1__nfs_3a_3anfs__mount__nfs(){
    nfs::nfs_mount { "nfs":

    }
}


node "ms1" {

    class {'litp::ms_node':}


    class {'task_ms1__cfg_3a_3aconfig__cfg':
        require => [Class["task_ms1__nfs_3a_3anfs__mount__nfs"]]
    }


    class {'task_ms1__cfg_3a_3afw__fw':
    }


    class {'task_ms1__nfs_3a_3anfs__mount__nfs':
        require => [Class["task_ms1__cfg_3a_3afw__fw"]]
    }


}