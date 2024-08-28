class litp::httpd ( $ms_hostname = 'ms1' ) {
  $_ms_hostname = $ms_hostname

  package { 'httpd': ensure => installed }

  service { 'httpd':
    ensure => running,
    enable => true,
  }
  file {'/etc/httpd/conf.d/ssl.conf':
    ensure  => file,
    content => "#file no longer needed as port 443 is no longer being listened to. Configuration to be left blank",
    notify  => Service[httpd]
  }
}