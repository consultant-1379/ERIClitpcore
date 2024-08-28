class task_ms1__ms_3a_3aconfigs__id__ms__config(){
    ms::configs { "id_ms_config":

    }
}

class task_ms1__ms_3a_3afile__systems__id__ms__file(){
    ms::file_systems { "id_ms_file":

    }
}

class task_ms1__ms_3a_3aitems__id__ms__item(){
    ms::items { "id_ms_item":

    }
}


node "ms1" {

    class {'litp::ms_node':}


    class {'task_ms1__ms_3a_3aconfigs__id__ms__config':
        require => [Class["task_ms1__ms_3a_3afile__systems__id__ms__file"]]
    }


    class {'task_ms1__ms_3a_3afile__systems__id__ms__file':
    }


    class {'task_ms1__ms_3a_3aitems__id__ms__item':
        require => [Class["task_ms1__ms_3a_3aconfigs__id__ms__config"]]
    }


}
