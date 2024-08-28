require 'facter'
Facter.add(:puppet_master) do
  setcode "[ -f /etc/sysconfig/puppetserver ] && echo 'true' || echo 'false'"
end
