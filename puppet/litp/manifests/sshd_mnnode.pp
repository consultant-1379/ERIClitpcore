define litp::sshd_mnnode ( $cluster_type ) {

    package {"openssh-server":
        ensure  => "installed",
    }

    litp::sshd_common { "sshd_mnnode_config":
        require => Package["openssh-server"],
    }

    if $cluster_type == "CMW" {
        $permitrootlogin = "set PermitRootLogin without-password"

        exec { "disable aging password for CMW cluster node only":
           command  => "/usr/bin/chage -I -1 -m 0 -M 99999 -E -1 root",
        }
    }
    else {
        $permitrootlogin = "set PermitRootLogin no"
    }

    augeas { "sshd_login_config":
        context => "/files/etc/ssh/sshd_config",
        changes => [
          $permitrootlogin,
        ],
        notify  => Service["sshd"],
    }
}

