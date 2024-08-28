
class task_node1__package__call__id___41(){
    package { "call_id_A":
        test_item_view => "PREFIX_Y.Y.Y_SUFFIX"
    }
}

class task_node1__package__view__trigger(){
    package { "view_trigger":
        version => "Y.Y.Y"
    }
}


node "node1" {

    class {'litp::mn_node':
        ms_hostname => "ms1",
        cluster_type => "NON-CMW"
        }


    class {'task_node1__package__call__id___41':
        require => [Class["task_node1__package__view__trigger"]]
    }


    class {'task_node1__package__view__trigger':
    }


}