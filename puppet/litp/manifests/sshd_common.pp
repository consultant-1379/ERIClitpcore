define litp::sshd_common {

    service { "sshd" :
        ensure  => "running",
        enable  => "true",
    }

    augeas { "sshd_banner_config" :
        context => "/files/etc/ssh/sshd_config",
        changes => [
            "set Banner /etc/issue.net",
        ],
        notify  => Service["sshd"]
   }
}
