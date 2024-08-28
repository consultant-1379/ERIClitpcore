
define yum::update {

  exec { 'yum_update':
    command => '/usr/bin/yum update',
    path    => '/usr/sbin:/bin',
  }

}
