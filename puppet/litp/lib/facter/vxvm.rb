##############################################################################
## COPYRIGHT Ericsson AB 2014
##
## The copyright to the computer program(s) herein is the property of
## Ericsson AB. The programs may be used and/or copied only with written
## permission from Ericsson AB. or in accordance with the terms and
## conditions stipulated in the agreement/contract under which the
## program(s) have been supplied.
###############################################################################

# Set of facts that return a imported disk group list
# 
#
#
require 'facter'


vxfs_loaded = Facter::Util::Resolution.exec("grep -e \"^vxfs.*\" /proc/modules")

if !vxfs_loaded.to_s.empty?
    groups = Facter::Util::Resolution.exec("vxdg list | awk \'{print $1}\' | sed \'1d\' | tr \"\n\" ','| sed 's/.$//'")
    if !groups.to_s.empty?
        Facter.add("vxvm_dg") do
            setcode do
                groups
            end
        end
    end
end
