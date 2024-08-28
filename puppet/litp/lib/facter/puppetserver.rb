##################################################################
# COPYRIGHT Ericsson AB 2019
#
# The copyright to the computer program(s) herein is the property
# of Ericsson AB. The programs may be used and/or copied only with
# written permission from Ericsson AB. or in accordance with the
# terms and conditions stipulated in the agreement/contract under
# which the program(s) have been supplied.
##################################################################
require 'facter'

is_virtual = false
heap_size = 2
target_virtual_mem = 4
target_physical_mem = 25

manufacturer = Facter.value(:manufacturer).downcase
["vmware", "virtualbox", "kvm", "qemu", "red hat"].each do |vapp_type|
    if manufacturer =~ /#{vapp_type}/
      is_virtual = true
      break
    end
end
if is_virtual
    total_memory = Facter.value(:memorysize).to_i()
    if total_memory > target_virtual_mem
      heap_size = target_virtual_mem
    end
else
    heap_size = target_physical_mem
end
Facter.add("puppetserver_heap_gb") do
    setcode do
      heap_size
    end
end
