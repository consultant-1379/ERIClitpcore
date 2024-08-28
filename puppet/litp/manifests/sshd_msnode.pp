define litp::sshd_msnode ( $permitrootlogin=no ) {
    augeas { "sshd_login_config":
        context => "/files/etc/ssh/sshd_config",
        changes => ["set PermitRootLogin $permitrootlogin"],
        notify => Service["sshd"],
    }
}
