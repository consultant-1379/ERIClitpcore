define litp::versionlock ($excluded_packages="None") {

  file { '/etc/yum/pluginconf.d/versionlock.list.packages':
    path    => '/etc/yum/pluginconf.d/versionlock.list.packages',
    content => template('litp/versionlock.list.packages.erb'),
    owner   => 'root',
    group   => 'root',
  } ~>
  exec { 'update_version_lock':
    command => '/bin/cat /etc/yum/pluginconf.d/versionlock.list.default \
    /etc/yum/pluginconf.d/versionlock.list.packages > \
    /etc/yum/pluginconf.d/versionlock.list',
    provider => shell,
    require => File['/etc/yum/pluginconf.d/versionlock.list.packages'],
    refreshonly => true,
  } ~>
  exec { "sleep":
   command => 'sleep 2',
   unless => '/usr/bin/[ -f /etc/yum/pluginconf.d/versionlock.list ]',
   provider => shell
  } ->
  Package <| |>

}
