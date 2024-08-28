# Class to manage the contents of /etc/puppet/puppet.conf

class litp::litp_puppet_conf () {

  $puppet_conf_file = '/etc/puppet/puppet.conf'

  ini_setting { 'set puppet certname to hostname':
    ensure  => present,
    path    => $puppet_conf_file,
    section => 'agent',
    setting => 'certname',
    value   => downcase("${::hostname}"),
  }

  ini_setting { 'set puppet agent runinterval':
    ensure  => present,
    path    => $puppet_conf_file,
    section => 'agent',
    setting => 'runinterval',
    value   => '1800',
  }

  ini_setting { 'set puppet agent configtimeout':
    ensure  => present,
    path    => $puppet_conf_file,
    section => 'agent',
    setting => 'configtimeout',
    value   => '1720',
  }

  ini_setting { 'set puppet agent splay':
    ensure  => present,
    path    => $puppet_conf_file,
    section => 'agent',
    setting => 'splay',
    value   => 'true',
  }

  ini_setting { 'set puppet agent splay limit':
    ensure  => present,
    path    => $puppet_conf_file,
    section => 'agent',
    setting => 'splaylimit',
    value   => '1800',
  }

  ini_setting { 'set puppet strong ciphers':
    ensure  => present,
    path    => $puppet_conf_file,
    section => 'agent',
    setting => 'ciphers',
    value       => 'ECDHE-RSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-SHA384:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-SHA256',
  }
}
