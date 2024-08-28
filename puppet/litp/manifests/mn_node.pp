class litp::mn_node ($ms_hostname, $cluster_type) {
    include litp::common_node

    if ($operatingsystemmajrelease >= '7'){
        $daemonize = 0
        $agent_cmd = "/bin/sleep 10 ; /usr/bin/systemctl reload mcollective.service"
        $repo_3pp = "3pp_rhel$operatingsystemmajrelease"
    }
    else {
        $daemonize = 1
        $agent_cmd = "/bin/sleep 10 ; /etc/init.d/mcollective reload-agents"
        $repo_3pp = "3pp"
    }

    class { '::mcollective':
        middleware                => false,
        middleware_ssl            => true,
        middleware_hosts          => [ $ms_hostname ],
        middleware_user           => 'mcollective',
        middleware_password       => 'litpmcoll',
        middleware_admin_user     => 'admin',
        middleware_admin_password => 'litprabbitadmin',

        site_libdir         => '/opt/mcollective',
        server              => true,
        client              => false,
        connector           => 'rabbitmq',
        rabbitmq_vhost      => '/mcollective',
        main_collective     => 'mcollective',
        collectives         => 'mcollective',
        server_logfile      => '/var/log/mcollective.log',
        server_loglevel     => 'info',
        client_loglevel     => 'error',
        server_daemonize    => $daemonize,
        securityprovider    => 'psk',
        psk                 => 'unset',
        ssl_server_private  => "${settings::privatekeydir}/${clientcert}.pem",
    }

    mcollective::server::setting { 'sslca_setting':
        setting => 'plugin.rabbitmq.pool.1.ssl.ca',
        value   => "${settings::certdir}/ca.pem",
    }

    mcollective::server::setting { 'sslcert_setting':
        setting => 'plugin.rabbitmq.pool.1.ssl.cert',
        value   => "${settings::certdir}/${clientcert}.pem",
    }

    mcollective::server::setting { 'sslkey_setting':
        setting => 'plugin.rabbitmq.pool.1.ssl.key',
        value   => "${settings::privatekeydir}/${clientcert}.pem",
    }

    exec { "mcollective-reload-agents":
        command     => $agent_cmd,
        refreshonly => true,
        require     => Service[mcollective],
    }

    file { "/opt/mcollective/mcollective/agent":
        ensure  => directory,
        source  => "puppet:///modules/mcollective_agents",
        recurse => true,
        purge   => true,
        ignore      => ['*.pyc', '*.pyo'],
        notify  => Exec['mcollective-reload-agents'],
    }

    file { "/opt/mcollective/mcollective/util":
        ensure  => directory,
        source  => "puppet:///modules/mcollective_utils",
        recurse => true,
        notify  => Service[mcollective],
    }

    yumrepo {'3PP':
        baseurl     => "http://$ms_hostname/$repo_3pp",
        descr       => "Third-Party Packages for LITP",
        enabled     => "1",
        gpgcheck    => '0',
    }

    yumrepo {'LITP':
        baseurl     => "http://$ms_hostname/litp",
        descr       => "LITP Packages",
        enabled     => "1",
        gpgcheck    => '0',
    }

    yumrepo {'OS':
        baseurl     => "http://$ms_hostname/$operatingsystemmajrelease/os/x86_64/Packages",
        descr       => "RHEL Packages",
        enabled     => "1",
        gpgcheck    => '0',
    }

    yumrepo {'UPDATES':
        baseurl     => "http://$ms_hostname/$operatingsystemmajrelease/updates/x86_64/Packages",
        descr       => "RHEL Packages",
        enabled     => "1",
        gpgcheck    => '0',
    }

    litp::sshd_mnnode { "sshd_mnode_config":
        cluster_type    => $cluster_type
    }

    user { 'litp-admin':
        ensure      => 'present',
        comment     => 'litp-admin',
        groups      => ['litp-admin'],
        home        => '/home/litp-admin',
        shell       => '/bin/bash',
    }

    if ($operatingsystemmajrelease >= '7'){
        file { 'local-selinux-policies-dir':
            ensure  => directory,
            owner   => 'root',
            group   => 'root',
            mode    => '0700',
            path    => '/var/SELinux',
        }

        file { 'local-selinux-policy-te':
            ensure  => 'file',
            owner   => 'root',
            group   => 'root',
            mode    => '0600',
            path    => '/var/SELinux/local.te',
            content => template('litp/local-selinux-policy-te.erb'),
            require => File['local-selinux-policies-dir'],
        }

        exec { 'local-selinux-set-bool':
            path     => '/sbin:/bin:/usr/bin:/usr/sbin',
            provider => shell,
            unless   => "test $(getsebool haproxy_connect_any | awk '{print \$NF}') == 'on'",
            command  => 'setsebool -P haproxy_connect_any 1',
        }

        exec { 'local-selinux-set-filetype':
            path     => '/sbin:/bin:/usr/bin:/usr/sbin',
            provider => shell,
            unless   => "test ! -f /ericsson/3pp/haproxy/data/config/haproxy-int.cfg || test $(ls -Z /ericsson/3pp/haproxy/data/config/haproxy-int.cfg | awk -F ':' '{print \$3}') == 'haproxy_unit_file_t'",
            command  => 'semanage fcontext -a -t haproxy_unit_file_t /ericsson/3pp/haproxy/data/config/haproxy-int.cfg && restorecon /ericsson/3pp/haproxy/data/config/haproxy-int.cfg',
        }

        exec { 'local-selinux-policy-compile':
            path        => '/sbin:/bin:/usr/bin:/usr/sbin',
            provider    => shell,
            command     => 'checkmodule -M -m -o /var/SELinux/local.mod /var/SELinux/local.te && chmod 600 /var/SELinux/local.mod',
            subscribe   => File['/var/SELinux/local.te'],
            refreshonly => true,
            notify      => Exec['local-selinux-policy-package'],
        }

        exec { 'local-selinux-policy-package':
            path        => '/sbin:/bin:/usr/bin:/usr/sbin',
            provider    => shell,
            refreshonly => true,
            command     => 'semodule_package -o /var/SELinux/local.pp -m /var/SELinux/local.mod && chmod 600 /var/SELinux/local.pp',
            notify      => Exec['local-selinux-policy-install'],
        }

        exec { 'local-selinux-policy-install':
            path        => '/sbin:/bin:/usr/bin:/usr/sbin',
            provider    => shell,
            refreshonly => true,
            command     => 'semodule -i /var/SELinux/local.pp',
        }
    }
}
