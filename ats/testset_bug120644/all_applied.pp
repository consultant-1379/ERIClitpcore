
class task_ms1__srv__image__ms__vmservice1(){
    srv_image { "ms_vmservice1":

    }
}


node "ms1" {

    class {'litp::ms_node':}


    class {'task_ms1__srv__image__ms__vmservice1':
    }


}
