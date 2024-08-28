class yum::permanentrepos (
                  $host='ms1'
                ) {

file { 'permanentrepos':
    ensure  => 'file',
    path    => "/etc/yum.repos.d/permanentrepos.repo",
    content => template('yum/permanentrepos.erb'),
    owner  => root,
    group  => root,
    mode   => '0644',
}

package { 'yum-utils':
    ensure     => 'present',
    require    => File['permanentrepos'],
}

}
