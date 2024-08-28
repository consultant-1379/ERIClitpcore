class litp::common_node {

    include litp::litp_puppet_conf

    $ssl_basepath = "/opt/ericsson/nms/litp/etc/ssl"

    group{ 'litp-admin':
        ensure      => 'present',
    }

    mcollective::server::setting { 'ciphers':
        setting     => 'plugin.rabbitmq.pool.1.ssl.ciphers',
        value       => 'ECDHE-RSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-SHA384:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-SHA256',
    }

    # increase intervals in range .1 - 30 s by 2 each time
    # do not time out, let mcollective keep retrying forever
    mcollective::server::setting { 'reconnect_attempts_setting':
        setting     => 'plugin.rabbitmq.max_reconnect_attempts',
        value       => 0,
    }

    mcollective::client::setting { 'reconnect_attempts_setting':
        setting     => 'plugin.rabbitmq.max_reconnect_attempts',
        value       => 21,
    }

    mcollective::server::setting { 'initial_reconnect_delay':
        setting     => 'plugin.rabbitmq.initial_reconnect_delay',
        value       => '0.1',
    }

    mcollective::server::setting { 'max_reconnect_delay':
        setting     => 'plugin.rabbitmq.max_reconnect_delay',
        value       => '3',
    }

    mcollective::server::setting { 'heartbeat_interval_setting':
        setting     => 'plugin.rabbitmq.heartbeat_interval',
        value       => 30,
    }

    mcollective::client::setting { 'heartbeat_interval_setting':
        setting     => 'plugin.rabbitmq.heartbeat_interval',
        value       => 30,
    }

    file { '/etc/yum/pluginconf.d/subscription-manager.conf':
        content     => "[main]\nenabled=0"
    }

    file { "/etc/cron.daily/rhsmd":
        ensure => absent,
    }

    file { '/etc/yum/pluginconf.d/versionlock.list.default':
        path        => '/etc/yum/pluginconf.d/versionlock.list.default',
        content     => template('litp/versionlock.list.default.erb'),
        owner       => 'root',
        group       => 'root',
        notify      => Exec['update_default_list'],
    }

    exec { 'delete_empty_version_lock':
        command     => '/bin/rm /etc/yum/pluginconf.d/versionlock.list',
        provider    => shell,
        notify      => Exec['init_version_lock'],
        onlyif      => '/usr/bin/test $(stat -c %s /etc/yum/pluginconf.d/versionlock.list) = 0',
    }

    exec { 'init_version_lock':
        command     => '/bin/cat /etc/yum/pluginconf.d/versionlock.list.default > \
        /etc/yum/pluginconf.d/versionlock.list',
        provider    => shell,
        require     => File['/etc/yum/pluginconf.d/versionlock.list.default'],
        creates     => '/etc/yum/pluginconf.d/versionlock.list',
    }

    exec { 'update_default_list':
        command     => "/bin/sed -i '/EXTRlitp/d' /etc/yum/pluginconf.d/versionlock.list",
        provider    => shell,
        onlyif      => "/usr/bin/[ -f /etc/yum/pluginconf.d/versionlock.list ]",
        refreshonly => true,
    }

    file { '/etc/modprobe.d/litp.conf':
        path        => '/etc/modprobe.d/litp.conf',
        ensure      => file,
        content     => template('litp/litp.conf.erb'),
        owner       => 'root',
        group       => 'root',
    }

    # TORF-662570 Ciscat changes for cron job
    file { "/etc/cron.d":
        ensure      => directory,
        mode       => '0700'
    }

    # TORF-662570 Ciscat changes for cron job
    file { "/etc/cron.daily":
        ensure      => directory,
        mode       => '0700'
    }

    # TORF-662570 Ciscat changes for cron job
    file { "/etc/cron.hourly":
        ensure      => directory,
        mode       => '0700'
    }

    # TORF-662570 Ciscat changes for cron job
    file { "/etc/cron.monthly":
        ensure      => directory,
        mode       => '0700'
    }

    # TORF-662570 Ciscat changes for cron job
    file { "/etc/cron.weekly":
        ensure      => directory,
        mode       => '0700'
    }

    # TORF-662570 Ciscat changes for cron job
    file { "/etc/crontab":
        ensure      => file,
        mode       => '0600'
    }

    # TORF-662570 Ciscat changes for cron job
    file {'/etc/cron.deny':
            ensure      => absent
    }

    # TORF-662570 Ciscat changes for cron job
    file { '/etc/cron.allow':
      ensure        => 'present',
      owner         => 'root',
      group         => 'root',
      mode         => '0600'
    }

    # TORF-652080 Disable unbound-anchor.timer
    service {'unbound-anchor.timer':
        ensure      => stopped,
        enable      => false,
    }

    file { '/etc/motd':
        ensure      => file,
        mode    => "0644",
        source => ["puppet:///modules/litp/motd.custom", "puppet:///modules/litp/motd"]
    }

    file { '/etc/issue.net':
        ensure  => file,
        mode    => "0644",
        source => ["puppet:///modules/litp/issue.net.custom", "puppet:///modules/litp/issuenet"]
    }

    file { '/etc/issue':
        ensure  => file,
        mode    => "0644",
        source => ["puppet:///modules/litp/issue.custom", "puppet:///modules/litp/issue"]
    }

    file { '/root/.cleanup_path.sh':
        ensure => file,
        source => 'puppet:///modules/common_node/cleanup_path.sh',
        mode   => '0755',
        owner  => 'root',
        group  => 'root',
    }

    exec { "update_root_bash_profile":
        command => 'echo "if [ -f ~/.cleanup_path.sh ]; then . ~/.cleanup_path.sh; fi" >> /root/.bash_profile',
        unless  => 'grep -q ".cleanup_path.sh" /root/.bash_profile',
        path    => ['/bin', '/usr/bin'],
        user    => 'root',
    }

    exec { 'run_cleanup_path':
        command => '/root/.cleanup_path.sh',
        require => File['/root/.cleanup_path.sh'],
    }

    exec { 'remove_group_write_permission':
        command => 'chmod g-w /opt/Unisphere/bin',
        onlyif  => '/usr/bin/test -d /opt/Unisphere/bin',
        path    => '/bin:/usr/bin',
    }

    define selinux_audit_rule ($line) {
        file_line { $name:
    	    path   => '/etc/audit/rules.d/audit.rules',
            line   => $line,
            ensure => present,
        }
    }

    selinux_audit_rule { '-a never,user -F subj_type=crond_t':
        line => '-a never,user -F subj_type=crond_t',
    }

    selinux_audit_rule { '-a exit,never -F subj_type=crond_t':
        line => '-a exit,never -F subj_type=crond_t',
    }

    selinux_audit_rule { '-w /etc/selinux/ -p wa -k MAC-policy':
        line => '-w /etc/selinux/ -p wa -k MAC-policy',
    }

    selinux_audit_rule { '-w /usr/share/selinux/ -p wa -k MAC-policy':
        line => '-w /usr/share/selinux/ -p wa -k MAC-policy',
    }

    selinux_audit_rule { '-w /etc/sudoers -p wa -k scope':
        line => '-w /etc/sudoers -p wa -k scope',
    }

    selinux_audit_rule { '-w /etc/sudoers.d/ -p wa -k scope':
        line => '-w /etc/sudoers.d/ -p wa -k scope',
    }

    selinux_audit_rule { '-a always,exit -F arch=b64 -S chmod -S fchmod -S fchmodat -F auid>=1000 -F auid!=4294967295 -k perm_mod':
        line => '-a always,exit -F arch=b64 -S chmod -S fchmod -S fchmodat -F auid>=1000 -F auid!=4294967295 -k perm_mod',
    }

    selinux_audit_rule { '-a always,exit -F arch=b32 -S chmod -S fchmod -S fchmodat -F auid>=1000 -F auid!=4294967295 -k perm_mod':
        line => '-a always,exit -F arch=b32 -S chmod -S fchmod -S fchmodat -F auid>=1000 -F auid!=4294967295 -k perm_mod',
    }

    selinux_audit_rule { '-a always,exit -F arch=b64 -S chown -S fchown -S fchownat -S lchown -F auid>=1000 -F auid!=4294967295 -k perm_mod':
        line => '-a always,exit -F arch=b64 -S chown -S fchown -S fchownat -S lchown -F auid>=1000 -F auid!=4294967295 -k perm_mod',
    }

    selinux_audit_rule { '-a always,exit -F arch=b32 -S chown -S fchown -S fchownat -S lchown -F auid>=1000 -F auid!=4294967295 -k perm_mod':
        line => '-a always,exit -F arch=b32 -S chown -S fchown -S fchownat -S lchown -F auid>=1000 -F auid!=4294967295 -k perm_mod',
    }

    selinux_audit_rule { '-a always,exit -F arch=b64 -S setxattr -S lsetxattr -S fsetxattr -S removexattr -S lremovexattr -S fremovexattr -F auid>=1000 -F auid!=4294967295 -k perm_mod':
        line => '-a always,exit -F arch=b64 -S setxattr -S lsetxattr -S fsetxattr -S removexattr -S lremovexattr -S fremovexattr -F auid>=1000 -F auid!=4294967295 -k perm_mod',
    }

    selinux_audit_rule { '-a always,exit -F arch=b32 -S setxattr -S lsetxattr -S fsetxattr -S removexattr -S lremovexattr -S fremovexattr -F auid>=1000 -F auid!=4294967295 -k perm_mod':
        line => '-a always,exit -F arch=b32 -S setxattr -S lsetxattr -S fsetxattr -S removexattr -S lremovexattr -S fremovexattr -F auid>=1000 -F auid!=4294967295 -k perm_mod',
    }

    selinux_audit_rule { '-a always,exit -F arch=b64 -S adjtimex -S settimeofday -k time-change':
        line => '-a always,exit -F arch=b64 -S adjtimex -S settimeofday -k time-change',
    }

    selinux_audit_rule { '-a always,exit -F arch=b32 -S adjtimex -S settimeofday -S stime -k time-change':
        line => '-a always,exit -F arch=b32 -S adjtimex -S settimeofday -S stime -k time-change',
    }

    selinux_audit_rule { '-a always,exit -F arch=b64 -S clock_settime -k time-change':
        line => '-a always,exit -F arch=b64 -S clock_settime -k time-change',
    }

    selinux_audit_rule { '-a always,exit -F arch=b32 -S clock_settime -k time-change':
        line => '-a always,exit -F arch=b32 -S clock_settime -k time-change',
    }

    selinux_audit_rule { '-w /etc/localtime -p wa -k time-change':
        line => '-w /etc/localtime -p wa -k time-change',
    }

    selinux_audit_rule { '-a always,exit -F arch=b64 -S sethostname -S setdomainname -k system-locale':
        line => '-a always,exit -F arch=b64 -S sethostname -S setdomainname -k system-locale',
    }

    selinux_audit_rule { '-a always,exit -F arch=b32 -S sethostname -S setdomainname -k system-locale':
        line => '-a always,exit -F arch=b32 -S sethostname -S setdomainname -k system-locale',
    }

    selinux_audit_rule { '-w /etc/issue -p wa -k system-locale':
        line => '-w /etc/issue -p wa -k system-locale',
    }

    selinux_audit_rule { '-w /etc/issue.net -p wa -k system-locale':
        line => '-w /etc/issue.net -p wa -k system-locale',
    }

    selinux_audit_rule { '-w /etc/hosts -p wa -k system-locale':
        line => '-w /etc/hosts -p wa -k system-locale',
    }

    selinux_audit_rule { '-w /etc/sysconfig/network -p wa -k system-locale':
        line => '-w /etc/sysconfig/network -p wa -k system-locale',
    }

    selinux_audit_rule { '-w /etc/group -p wa -k identity':
        line => '-w /etc/group -p wa -k identity',
    }

    selinux_audit_rule { '-w /etc/passwd -p wa -k identity':
        line => '-w /etc/passwd -p wa -k identity',
    }

    selinux_audit_rule { '-w /etc/gshadow -p wa -k identity':
        line => '-w /etc/gshadow -p wa -k identity',
    }

    selinux_audit_rule { '-w /etc/shadow -p wa -k identity':
        line => '-w /etc/shadow -p wa -k identity',
    }

    selinux_audit_rule { '-w /etc/security/opasswd -p wa -k identity':
        line => '-w /etc/security/opasswd -p wa -k identity',
    }

    selinux_audit_rule { '-a always,exit -F arch=b64 -S unlink -S unlinkat -S rename -S renameat -F auid>=1000 -F auid!=4294967295 -k delete':
        line => '-a always,exit -F arch=b64 -S unlink -S unlinkat -S rename -S renameat -F auid>=1000 -F auid!=4294967295 -k delete',
    }

    selinux_audit_rule { '-a always,exit -F arch=b32 -S unlink -S unlinkat -S rename -S renameat -F auid>=1000 -F auid!=4294967295 -k delete':
        line => '-a always,exit -F arch=b32 -S unlink -S unlinkat -S rename -S renameat -F auid>=1000 -F auid!=4294967295 -k delete',
    }

    selinux_audit_rule { '-w /sbin/insmod -p x -k modules':
        line => '-w /sbin/insmod -p x -k modules',
    }

    selinux_audit_rule { '-w /sbin/rmmod -p x -k modules':
        line => '-w /sbin/rmmod -p x -k modules',
    }

    selinux_audit_rule { '-w /sbin/modprobe -p x -k modules':
        line => '-w /sbin/modprobe -p x -k modules',
    }

    selinux_audit_rule { '-a always,exit -F arch=b32 -S init_module -S delete_module -k modules':
        line => '-a always,exit -F arch=b32 -S init_module -S delete_module -k modules',
    }

    selinux_audit_rule { '-a always,exit -F arch=b64 -S init_module -S delete_module -k modules':
        line => '-a always,exit -F arch=b64 -S init_module -S delete_module -k modules',
    }

    selinux_audit_rule { '-w /var/log/lastlog -p wa -k logins':
        line => '-w /var/log/lastlog -p wa -k logins',
    }

    selinux_audit_rule { '-w /var/run/faillock/ -p wa -k logins':
        line => '-w /var/run/faillock/ -p wa -k logins',
    }

    selinux_audit_rule { '-w /var/run/utmp -p wa -k session':
        line => '-w /var/run/utmp -p wa -k session',
    }

    selinux_audit_rule { '-w /var/log/wtmp -p wa -k logins':
        line => '-w /var/log/wtmp -p wa -k logins',
    }

    selinux_audit_rule { '-w /var/log/btmp -p wa -k logins':
        line => '-w /var/log/btmp -p wa -k logins',
    }

    selinux_audit_rule { '-a always,exit -F arch=b64 -S mount -F auid>=1000 -F auid!=4294967295 -k mounts':
        line => '-a always,exit -F arch=b64 -S mount -F auid>=1000 -F auid!=4294967295 -k mounts',
    }

    selinux_audit_rule { '-a always,exit -F arch=b32 -S mount -F auid>=1000 -F auid!=4294967295 -k mounts':
        line => '-a always,exit -F arch=b32 -S mount -F auid>=1000 -F auid!=4294967295 -k mounts',
    }

    selinux_audit_rule { '-a always,exit -F arch=b64 -C euid!=uid -F euid=0 -F auid>=1000 -F auid!=4294967295 -S execve -k actions':
        line => '-a always,exit -F arch=b64 -C euid!=uid -F euid=0 -F auid>=1000 -F auid!=4294967295 -S execve -k actions',
    }

    selinux_audit_rule { '-a always,exit -F arch=b32 -C euid!=uid -F euid=0 -F auid>=1000 -F auid!=4294967295 -S execve -k actions':
        line => '-a always,exit -F arch=b32 -C euid!=uid -F euid=0 -F auid>=1000 -F auid!=4294967295 -S execve -k actions',
    }

    selinux_audit_rule { '-a always,exit -F arch=b64 -S creat -S open -S openat -S truncate -S ftruncate -F exit=-EACCES -F auid>=1000 -F auid!=4294967295 -k access':
        line => '-a always,exit -F arch=b64 -S creat -S open -S openat -S truncate -S ftruncate -F exit=-EACCES -F auid>=1000 -F auid!=4294967295 -k access',
    }

    selinux_audit_rule { '-a always,exit -F arch=b32 -S creat -S open -S openat -S truncate -S ftruncate -F exit=-EACCES -F auid>=1000 -F auid!=4294967295 -k access':
        line => '-a always,exit -F arch=b32 -S creat -S open -S openat -S truncate -S ftruncate -F exit=-EACCES -F auid>=1000 -F auid!=4294967295 -k access',
    }

    selinux_audit_rule { '-a always,exit -F arch=b64 -S creat -S open -S openat -S truncate -S ftruncate -F exit=-EPERM -F auid>=1000 -F auid!=4294967295 -k access':
        line => '-a always,exit -F arch=b64 -S creat -S open -S openat -S truncate -S ftruncate -F exit=-EPERM -F auid>=1000 -F auid!=4294967295 -k access',
    }

    selinux_audit_rule { '-a always,exit -F arch=b32 -S creat -S open -S openat -S truncate -S ftruncate -F exit=-EPERM -F auid>=1000 -F auid!=4294967295 -k access':
        line => '-a always,exit -F arch=b32 -S creat -S open -S openat -S truncate -S ftruncate -F exit=-EPERM -F auid>=1000 -F auid!=4294967295 -k access',
    }

    exec { 'reload_audit_rules':
        command     => '/sbin/auditctl -R /etc/audit/rules.d/audit.rules',
    }

    $script_source_path = 'puppet:///modules/common_node/partition_rules.sh'
    $script_dest_path   = '/usr/local/bin/partition_rules.sh'


    file { $script_dest_path:
        ensure => file,
        source => $script_source_path,
        mode   => '0755',
        owner  => 'root',
        group  => 'root',
    }

    exec { 'update_audit_rules':
        command     => $script_dest_path,
        refreshonly => true,
        subscribe   => File[$script_dest_path],
    }

    exec { 'reload_privileged_rules':
        command     => $script_dest_path,
    }

    exec { 'reload_40_litp_rules':
        command     => '/sbin/auditctl -R /etc/audit/rules.d/40-litp.rules',
    }


    package { 'yum-plugin-post-transaction-actions':
        ensure => installed,
    }

    file { '/etc/yum/pluginconf.d/post-transaction-actions.conf':
        ensure  => file,
        content => "[main]\nenabled = 1\nactiondir = /etc/yum/post-actions/",
        owner   => 'root',
        group   => 'root',
        mode    => '0644',
    }

    file { '/etc/yum/post-actions/':
        ensure => directory,
        owner  => 'root',
        group  => 'root',
        mode   => '0755',
    }

    file { '/etc/yum/post-actions/audit.sh':
        ensure => file,
        source => 'puppet:///modules/common_node/audit.sh',
        mode   => '0755',
        owner  => 'root',
        group  => 'root',
    }


        file { '/etc/yum/post-actions/litp.action':
        ensure => file,
        owner  => 'root',
        group  => 'root',
        mode   => '0644',
    }

        file_line { 'litp_action_line':
        path   => '/etc/yum/post-actions/litp.action',
        line   => '*:install:/etc/yum/post-actions/audit.sh $action $name',
        ensure => present,
        require => File['/etc/yum/post-actions/litp.action'],
    }

}
