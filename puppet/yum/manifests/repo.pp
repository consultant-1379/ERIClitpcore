
define yum::repo (
                  $name,
                  $url
                ) {

  file { "yum_${name}":
    ensure  => 'file',
    path    => "/etc/yum.repos.d/${name}.repo",
    content => template('yum/yum.repo.erb'),
  }

}
