class litp::ms_node {
    include litp::common_node
    $ms_hostname = $hostname

    file { "$litp::common_node::ssl_basepath": ensure  => directory }

    class { '::mcollective':
        middleware                  => true,
        middleware_ssl              => true,
        middleware_hosts            => [ $ms_hostname ],
        middleware_cli_host         => '::1',
        middleware_user             => 'mcollective',
        middleware_password         => 'litpmcoll',
        middleware_admin_user       => 'admin',
        middleware_admin_password   => 'litprabbitadmin',
        delete_guest_user           => false,

        site_libdir                 => '/opt/ericsson/nms/litp/etc/mcollective',
        server                      => true,
        client                      => true,
        connector                   => 'rabbitmq',
        rabbitmq_confdir            => '/etc/rabbitmq/ssl',
        rabbitmq_vhost              => '/mcollective',
        main_collective             => 'mcollective',
        collectives                 => 'mcollective',
        server_logfile              => '/var/log/mcollective.log',
        server_loglevel             => 'info',
        loglevel                    => 'err',
        server_daemonize            => 0,
        securityprovider            => 'psk',
        psk                         => 'unset',
        ssl_ca_cert                 => '/var/lib/puppet/ssl/certs/ca.pem',
        ssl_server_public           => "$settings::hostcert",
        ssl_server_private          => "$settings::hostprivkey",
    }

    file { "/opt/ericsson/nms/litp/etc/puppet/modules/litp/files":
        ensure           => directory,
        owner            => 'root',
        group            => 'puppet',
        mode             => '0750',
    }

    file { "/opt/ericsson/nms/litp/etc/puppet/modules/litp/files/server_public.pem":
        source           => "/etc/mcollective/server_public.pem",
        owner            => 'root',
        group            => 'root',
        mode             => '0444',
        require          => [File["/opt/ericsson/nms/litp/etc/puppet/modules/litp/files"],
                             Class['::mcollective']],
    }

    file { "/opt/ericsson/nms/litp/etc/puppet/modules/litp/files/server_private.pem":
        source           => "/etc/mcollective/server_private.pem",
        owner            => 'root',
        group            => 'root',
        mode             => '0444',
        require          => [File["/opt/ericsson/nms/litp/etc/puppet/modules/litp/files"],
                             Class['::mcollective']],
    }

    mcollective::client::setting { 'collectives_setting':
        setting     => 'collectives',
        value       => 'mcollective',
    }

    mcollective::client::setting { 'maincol_setting':
        setting     => 'main_collective',
        value       => 'mcollective',
    }

    mcollective::client::setting { 'libdir_setting':
        setting     => 'libdir',
        value       => '/opt/ericsson/nms/litp/etc/mcollective:/usr/libexec/mcollective',
    }

    mcollective::client::setting { 'loggertype_setting':
        setting     => 'logger_type',
        value       => 'console',
    }

    mcollective::client::setting { 'loglevel_setting':
        setting     => 'loglevel',
        value       => 'error',
    }

    mcollective::client::setting { 'discovery_setting':
        setting     => 'default_discovery_method',
        value       => 'mc',
    }

    mcollective::client::setting { 'treshold_setting':
        setting     => 'direct_addressing_threshold',
        value       => '10',
    }

    mcollective::client::setting { 'ttl_setting':
        setting     => 'ttl',
        value       => '60',
    }

    mcollective::client::setting { 'rpclimitmethod_setting':
        setting     => 'rpclimitmethod',
        value       => 'first',
    }

    mcollective::client::setting { 'connector_setting':
        setting     => 'connector',
        value       => 'rabbitmq',
    }

    mcollective::client::setting { 'addressing_setting':
        setting     => 'direct_addressing',
        value       => '1',
    }

    mcollective::client::setting { 'host_setting':
        setting     => 'plugin.rabbitmq.pool.1.host',
        value       => '::1',
    }

    mcollective::client::setting { 'port_setting':
        setting     => 'plugin.rabbitmq.pool.1.port',
        value       => '61613',
    }

    file { ["/opt/ericsson",
            "/opt/ericsson/nms",
            "/opt/ericsson/nms/litp",
            "/opt/ericsson/nms/litp/etc"]:
        ensure      => directory,
    }

    class { 'litp::httpd':
        ms_hostname => $ms_hostname,
    }

    file { "/opt/ericsson/nms/litp/etc/puppet/modules/mcollective_agents":
        ensure      => directory,
    }

    file { "/opt/ericsson/nms/litp/etc/puppet/modules/mcollective_utils":
        ensure      => directory,
    }

    file { "/opt/ericsson/nms/litp/etc/puppet/modules/mcollective_agents/files":
        require     => File['/opt/ericsson/nms/litp/etc/puppet/modules/mcollective_agents'],
        ensure      => directory,
    }

    file { "/opt/ericsson/nms/litp/etc/puppet/modules/mcollective_utils/files":
        require     => File['/opt/ericsson/nms/litp/etc/puppet/modules/mcollective_utils'],
        ensure      => directory,
    }

    exec { "mcollective-reload-agents":
        command     => "/bin/sleep 10 ; /usr/bin/systemctl reload mcollective.service",
        refreshonly => true,
        require     => Service[mcollective]
    }

    file { "/opt/ericsson/nms/litp/etc/mcollective/mcollective/agent":
        ensure      => directory,
        owner       => celery,
        group       => puppet,
        source      => "puppet:///modules/mcollective_agents",
        recurse     => true,
        purge       => true,
        ignore      => ['*.pyc', '*.pyo'],
        notify      => Exec['mcollective-reload-agents']
    }

    file { "/opt/ericsson/nms/litp/etc/puppet/modules/cobblerdata/manifests":
        ensure      => directory,
        owner       => celery,
        group       => puppet,
        mode        => '0750',
        recurse     => true
    }

    file { "/opt/ericsson/nms/litp/etc/mcollective/mcollective/util":
        ensure      => directory,
        source      => "puppet:///modules/mcollective_utils",
        recurse     => true,
        notify      => Service[mcollective]
    }

    yumrepo {'3PP':
        baseurl     => "http://$ms_hostname/3pp_rhel$operatingsystemmajrelease",
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

    yumrepo {'LITP_PLUGINS':
        baseurl     => "http://$ms_hostname/litp_plugins",
        descr       => "Plugins for LITP",
        enabled     => "1",
        gpgcheck    => '0',
    }

    yumrepo {'OS':
        baseurl     => "http://$ms_hostname/7/os/x86_64/Packages",
        descr       => "RHEL Packages",
        enabled     => "1",
        gpgcheck    => '0',
        require     => File['/var/www/html/7/'],
    }

    yumrepo {'UPDATES':
        baseurl     => "http://$ms_hostname/7/updates/x86_64/Packages",
        descr       => "RHEL Packages",
        enabled     => "1",
        gpgcheck    => '0',
        require     => File['/var/www/html/7/'],
    }

    file { ["/var/www/html/7.9",
            "/var/www/html/7.9/os",
            "/var/www/html/7.9/os/x86_64",
            "/var/www/html/7.9/os/x86_64/Packages",
            "/var/www/html/7.9/updates",
            "/var/www/html/7.9/updates/x86_64",
            "/var/www/html/7.9/updates/x86_64/Packages",
            "/var/www/html/litp_plugins",
            "/var/www/html/vm_scripts"]:
        ensure      => directory,
    }

    file {'/var/www/html/7/':
        ensure      => 'link',
        target      => '/var/www/html/7.9/',
        require     => File["/var/www/html/7.9/updates"],
    }

    file { [ "/var/www/html/8.8",
             "/var/www/html/8.8/updates_AppStream",
             "/var/www/html/8.8/updates_AppStream/x86_64",
             "/var/www/html/8.8/updates_AppStream/x86_64/Packages",
             "/var/www/html/8.8/updates_BaseOS",
             "/var/www/html/8.8/updates_BaseOS/x86_64",
             "/var/www/html/8.8/updates_BaseOS/x86_64/Packages"]:
        ensure      => directory,
    }

    file { '/var/www/html/8/':
        ensure      => 'link',
        target      => '/var/www/html/8.8/',
        require     => File["/var/www/html/8.8/updates_AppStream"],
    }

    $ec_str = 'config_version = "/bin/cat /opt/ericsson/nms/litp/etc/puppet/litp_config_version"
manifest = /opt/ericsson/nms/litp/etc/puppet/manifests/plugins
modulepath = /opt/ericsson/nms/litp/etc/puppet/modules
'
    file {'/opt/ericsson/nms/litp/etc/puppet/environments/production/environment.conf':
        seluser     => 'system_u',
        ensure      => file,
        content     => $ec_str,
    }

    file {'/opt/ericsson/nms/litp/etc/puppet/manifests/plugins/site.pp':
        ensure     => 'absent',
    }

    service {'rsyslog':
        ensure      => running,
        enable      => true,
    }

    file_line {'rsyslog_update':
        path        => '/etc/rsyslog.conf',
        line        => '*.*;mail.none;authpriv.none;cron.none                /var/log/messages',
        match       => '^\*\..*\/var\/log\/messages$',
        notify      => Service['rsyslog'],
    }

    exec { 'restart_httpd_graceful':
        command     => '/usr/sbin/httpd -k graceful',
        refreshonly => true,
    }

    file {'/etc/logrotate.d/httpd':
        path        => '/etc/logrotate.d/httpd',
        content     => template('litp/httpd_logrotate.erb'),
        owner       => 'root',
        group       => 'root',
        notify      => Service[httpd],
    }

    augeas { 'httpd_config' :
          context   => "/files/etc/httpd/conf/httpd.conf",
          changes   => [
              "set directive[. = 'TraceEnable'] TraceEnable",
              "set directive[. = 'TraceEnable']/arg[1] Off",
              "set directive[. = 'ServerTokens'] ServerTokens",
              "set directive[. = 'ServerTokens']/arg[1] Prod",
              "set directive[. = 'ServerSignature'] ServerSignature",
              "set directive[. = 'ServerSignature']/arg[1] Off",
              "set directive[. = 'FileETag'] FileETag",
              "set directive[. = 'FileETag']/arg[1] None",
              "set directive[. = 'ServerName'] ServerName",
              "set directive[. = 'ServerName']/arg[1] $ms_hostname:80",
              "set Directory[arg = '\"/var/www/html\"']/directive[. = 'Options']/arg[1] -Indexes",
              "set Directory[arg = '\"/var/www/html\"']/directive[. = 'Options']/arg[2] +FollowSymLinks",
          ],
          notify    => Exec['restart_httpd_graceful']
    }

    augeas { 'httpd_autoindex_config' :
          context   => "/files/etc/httpd/conf.d/autoindex.conf",
          changes   => [
              "set Directory[arg = '\"/usr/share/httpd/icons\"']/directive[. = 'Options']/arg[1] -Indexes",
              "set Directory[arg = '\"/usr/share/httpd/icons\"']/directive[. = 'Options']/arg[2] +MultiViews",
              "set Directory[arg = '\"/usr/share/httpd/icons\"']/directive[. = 'Options']/arg[3] +FollowSymlinks",
          ],
          notify    => Exec['restart_httpd_graceful']
    }

    litp::sshd_common { "sshd_msnode_config": }

    class { 'postgresql_litp::globals':
      encoding => 'UTF-8',
      locale   => 'C',
      version  => '9.6',
      client_package_name => 'rh-postgresql96-postgresql',
      server_package_name => 'rh-postgresql96-postgresql-server',
      datadir => '/var/opt/rh/rh-postgresql96/lib/pgsql/data',
      bindir => '/usr/bin',
      service_name => 'rh-postgresql96-postgresql',
      require  => Class['::postgresql_litp::server'],
      ssl_cert_dir => '/var/opt/rh/rh-postgresql96/lib/pgsql/ssl',
    }

    package { ['rh-postgresql96-postgresql-server-syspaths', 'rh-postgresql96-postgresql-syspaths' ] :
        ensure => 'installed',
        require => [ Yumrepo['3PP'], Exec ['perform_postgres_migration_8.4.20_to_9.6.5'] ],
        before  => Class['::postgresql_litp::server'],
    }

    exec { 'perform_postgres_migration_8.4.20_to_9.6.5' :
        command => 'sh /opt/ericsson/nms/litp/bin/postgres_migration.sh',
        path    => '/bin:/usr/bin',
        creates => '/var/lib/pgsql/postgresql_rh-postresql96_migration_status_ok',
    }

    # Configure puppetdb and its underlying database
    class { 'puppetdb':
        # Add name for repackaged puppetdb
        puppetdb_package            => "EXTRlitppuppetdb_CXP9032594",
        ssl_listen_address          => "$::hostname",
        report_ttl                  => '30m',
        # Note: This interval pertains to stale information held in PuppetDB's
        # backing Postgres database, not to the memory space of the PuppetDB
        # process.
        gc_interval                 => '30',
    }

    # Configure the puppet master to use puppetdb
    class { 'puppetdb::master::config':
        # Add name for repackaged puppetdb-terminus
        terminus_package            => "EXTRlitppuppetdbterminus_CXP9032595",
        manage_report_processor     => true,
        enable_reports              => true,
        puppetdb_server             => "$::hostname",
        puppet_service_name         => "puppetserver",
     }

    postgresql_litp::server::role { "puppetdb":
        password_hash => 'md53cbf124486f5dca866b9eb0d6a3bb314',
    }

    postgresql_litp::server::role { "litp":
        password_hash => 'md507ee58eb387feb097a5edcdbd0928059',
    }

    postgresql_litp::server::database { "litp":
    }

    postgresql_litp::server::database_grant { "litp":
        privilege         => "ALL",
        db                => "litp",
        role              => "litp",
    }

    postgresql_litp::server::pg_hba_rule { "litp":
        type              => "hostssl",
        database          => "litp",
        user              => "litp",
        auth_method       => "cert",
        auth_option       => "clientcert=1",
        address           => "127.0.0.1/32",
        order             => "001",
    }

    postgresql_litp::server::pg_hba_rule { "litppostgres":
        type              => "hostssl",
        database          => "postgres",
        user              => "litp",
        auth_method       => "cert",
        auth_option       => "clientcert=1",
        address           => "127.0.0.1/32",
        order             => "002",
    }

    postgresql_litp::server::table_grant { "litppostgres":
        privilege => "select",
        table     => "pg_authid",
        db        => "postgres",
        role      => "litp",
    }

    postgresql_litp::server::database { "litpcelery":
    }

    postgresql_litp::server::database_grant { "litpcelery":
        privilege         => "ALL",
        db                => "litpcelery",
        role              => "litp",
    }

    postgresql_litp::server::pg_hba_rule { "litpcelery":
        type              => "hostssl",
        database          => "litpcelery",
        user              => "litp",
        auth_method       => "cert",
        auth_option       => "clientcert=1",
        address           => "127.0.0.1/32",
        order             => "001",
    }

    rabbitmq_vhost { "/litp":
        ensure => present,
        require => Service[rabbitmq-server],
    } ->

    rabbitmq_user { "litp":
        admin => false,
        password => 'ptil',
    } ->

    rabbitmq_user_permissions { 'litp@/litp':
        configure_permission => '.*',
        read_permission      => '.*',
        write_permission     => '.*',
    } ->

    service {'celery':
        ensure      => running,
        enable      => true,
    }

    service {'celerybeat':
        ensure      => running,
        enable      => true,
    }

    package { 'ERIClitpdocs_CXP9030557':
        ensure => 'absent',
    }

    file { 'remove-litp-docs-symlink':
        ensure => absent,
        path => '/var/www/html/docs',
        recurse => true,
        purge => true,
        force => true,
        require => Package['ERIClitpdocs_CXP9030557'],
    }

    file { 'remove-litp-docs-directory':
        ensure => absent,
        path => '/opt/ericsson/nms/litp/share/docs',
        recurse => true,
        purge => true,
        force => true,
        require => Package['ERIClitpdocs_CXP9030557'],
    }

    exec { 'remove-litp-docs-package-sync-repo':
        cwd => '/var/www/html/litp',
        path => ['/bin', '/usr/bin'],
        command => 'rm -f ERIClitpdocs_CXP9030557-*.rpm && createrepo --update . && yum clean all',
        refreshonly => true,
        subscribe => Package['ERIClitpdocs_CXP9030557'],
    }

    package{ 'mesa-libGL':
        ensure => installed,
        require => Yumrepo['OS'],
    }

    user { 'litp-admin':
        ensure      => 'present',
        comment     => 'litp-admin',
        groups      => ['litp-admin', 'celery'],
        home        => '/home/litp-admin',
        shell       => '/bin/bash',
    }

    file {'/usr/lib/tmpfiles.d/litpd.conf':
        ensure      => 'file',
        content     => 'd /var/run/litpd 0750 root litp-access',
        owner       => 'root',
        group       => 'root',
        mode        => '0644',
    }

    file {'/etc/at.deny':
            ensure      => absent
    }

    file {'/etc/at.allow':
        ensure      => present,
        mode        => '0600'
    }

    service {'puppetserver':
        enable      => true,
        ensure      => running,
    }

    include puppetserver::server_conf
}
