##############################################################################
## COPYRIGHT Ericsson AB 2014
##
## The copyright to the computer program(s) herein is the property of
## Ericsson AB. The programs may be used and/or copied only with written
## permission from Ericsson AB. or in accordance with the terms and
## conditions stipulated in the agreement/contract under which the
## program(s) have been supplied.
###############################################################################

# Set of facts that carry device ID and give back a path to the device.
# Paths may vary, depending on a multipather used. Either default linux
# multipath or Symantec Dynamic Multi-Pathing (DMP) will be used.
# DMP will be used in case of a sfha cluster.
#
# Most Facts carries a ID_SERIAL_SHORT as main part of name
#
# Example: $disk_6006016011602d00ac03b5856769e311_part2_dev => /dev/sda2
#
# IS_SERIAL_SHORT Example for different environments:
# LUN ID    : 6006016011602d00ac03b5856769e311
# QEMU      : drive-scsi0-0-0-0
# QEMU SATA : ATA_QEMU_HARDDISK_QM00001
# VBOX SATA : ATA_VBOX_HARDDISK_VBfa3d1e0b-0c7f37a6
require 'facter'

# all detected disks and partitions
disks_by_id = {}
vxvm_disks_by_id = {}
disks_wmp_by_id = {}

###################################################
# Create facts about disks available to the system
###################################################

vxvm_installed = File.exist?("/sbin/vxdisk")

path='/usr/lib/udev'
if (Facter.value(:operatingsystemmajrelease).to_i < 7)
    path = '/sbin'
end

scsi_id_cmd = "#{path}/scsi_id --export --whitelisted --device=%s | grep ID_SERIAL_SHORT | awk -F= '{print $2}'"

if File.exist?("/dev/disk/by-id") and Facter.value(:kernel) == "Linux" and Facter.value(:osfamily) == "RedHat"

  # scsi presented device
  # also LUNs if multipathing is not enabled
  scsi_disks = Facter::Util::Resolution.exec("find /dev/disk/by-id/ -name scsi-* -printf \"%p:%l\n\"")
  if scsi_disks.to_s.empty?
    # Nothing found. Give HP SmartArray a try (LITPCDS-8098).
    scsi_disks = Facter::Util::Resolution.exec("find /dev/disk/by-id/ -name cciss-* -printf \"%p:%l\n\"")
  end
  if !scsi_disks.to_s.empty?
    scsi_disks.lines.each do |line|
      id_path, dev_rel_path = line.split(":")
      part_match = /(-part(\d+))/
      matched = part_match.match(id_path)
      if matched and matched.size == 3
        # we got a partition
        part = matched[1]
        parent_dev = id_path[0..-(part.size+1)]
        id = Facter::Util::Resolution.exec(scsi_id_cmd % parent_dev)
        if !id.to_s.empty?
          id = id + part.gsub("-","_")
        end
      else
        id = Facter::Util::Resolution.exec(scsi_id_cmd % id_path)
      end
      dev = File.expand_path(dev_rel_path,"/dev/disk/by-id").chomp
      dev_name = dev.split("/dev/")[1].chomp

      # Skip this device if if has no IS_SERIAL_SHORT
      next if id.to_s.empty?

      id = id.gsub("-","_")
      if vxvm_installed
        vxvm_name = Facter::Util::Resolution.exec("/sbin/vxdisk list #{dev_name} 2>/dev/null | grep Device | cut -d':' -f2 | sed -e 's/^ *//' -e 's/ *$//'")
        if !vxvm_name.to_s.empty?
          vxvm_disks_by_id[id] = vxvm_name
        end
      end
      disks_wmp_by_id[id] = dev
      disks_by_id[id] = dev
    end
  end


  ###################################################
  # if multipathing is enabled (kernel module loaded)
  # assumed that user_friendly_names is enabled
  # look into /dev/mapper/ links
  ###################################################

  dm_multipath_loaded = Facter::Util::Resolution.exec("grep -e \"^dm_multipath.*\" /proc/modules")
  if !dm_multipath_loaded.to_s.empty? and File.exists?("/dev/mapper")
    mpath_disks = Facter::Util::Resolution.exec("find /dev/mapper -name \"mpath*\" -printf \"%p:%l\n\"")

    if !mpath_disks.to_s.empty?
      mpath_disks.lines.each do |line|
        id_path, dev_rel_path = line.split(":")
        # TODO(igor) Will this work for more than one letter device paths?
        part_match = /mpath([a-z])p?(\d)+/
        matched = part_match.match(id_path)
        if matched and matched.size == 3
          # we got a partition
          parent_dev = "/dev/mapper/mpath#{matched[1]}"
          # find serial of this disk
          id = Facter::Util::Resolution.exec(scsi_id_cmd % parent_dev)
          # and add this to id
          id += "_part#{matched[2]}"
        else
          id = Facter::Util::Resolution.exec(scsi_id_cmd % id_path)
        end

        dev = id_path # use /dev/mapper/ paths

        # Skip this device if if has no IS_SERIAL_SHORT
        next if id.to_s.empty?

        id = id.gsub("-","_")
        disks_by_id[id] = dev
      end
    end

  else

  #######################################################################################
  # Get dmp devices
  # examples @return:
  #   disk_ata_vbox_harddisk_vb546bd46f_bc114f32_dev => /dev/vx/dmp/sda
  #   disk_ata_vbox_harddisk_vb546bd46f_bc114f32_part1_dev => /dev/vx/dmp/sda1
  #   disk_ata_vbox_harddisk_vb546bd46f_bc114f32_part2_dev => /dev/vx/dmp/sda2
  #
  #   disk_6006016011602d00483bacade79fe411_dev => /dev/vx/dmp/emc_clariion0_141
  #   disk_6006016011602d00483bacade79fe411_part1_dev => /dev/vx/dmp/emc_clariion0_141s1
  #   disk_6006016011602d00483bacade79fe411_part2_dev => /dev/vx/dmp/emc_clariion0_141s2
  ########################################################################################

    if vxvm_installed

      # get a comma separated list of devices under dmp
      # example: /dev/vx/dmp/emc_clariion0_141,/dev/vx/dmp/emc_clariion0_141s2
      pvs_cmd = "/sbin/pvs --all --noheadings 2>/dev/null | grep dmp | awk '{print $1}' | paste -sd ','"
      pvs_disks = Facter::Util::Resolution.exec(pvs_cmd)

      if !pvs_disks.to_s.empty?
        pvs_disks_list = pvs_disks.split(',')

        disks_wmp_by_id.each do |disk_id, disk_dev|
          pvs_disks_list.each do |disk|
            # get disk uuid
            pvs_disk_id = Facter::Util::Resolution.exec(scsi_id_cmd % disk).gsub("-","_")

            # find disks with the same id as "pvs_disk_id"
            id_match = /#{pvs_disk_id}/
            id_matched = id_match.match(disk_id)
            next if id_matched.nil?

            # is partition?
            partition_match = /(_part(\d+))$/
            partition_matched = partition_match.match(disk_id)
            if partition_matched
              # get last digit(s) of partition_matched
              partition_digits_match = /(\d+)$/
              partition_digits_matched = partition_digits_match.match(partition_matched[1])

              if partition_digits_matched
                # get last digit(s) of disk, ex.: from disk "/dev/vx/dmp/sda2" get digit "2"
                disk_digits_match = /(\d+)$/
                disk_digits_matched = disk_digits_match.match(disk)

                 # match digits
                 next if disk_digits_matched[0] != partition_digits_matched[0]

                 disks_by_id[disk_id] = disk
              end
            else
              # When not a partition, use vxdmpadm cmd to get dev name
              pvs_disk_name = disk.split("/dev/vx/dmp/")[1]
              vxdmpadm_cmd = "/sbin/vxdmpadm list dmpnode dmpnodename=#{pvs_disk_name} | grep dmpdev | awk -F= '{print $2}' | awk '{print $1}'"

              dmp_dev_name = Facter::Util::Resolution.exec(vxdmpadm_cmd)
              if !dmp_dev_name.to_s.empty?
                dmp_dev_name = dmp_dev_name.chomp
                disks_by_id[disk_id] = "/dev/vx/dmp/" + dmp_dev_name
              end
            end
          end
        end
      end
    end
  end

  #######################################################################
  # create new facts, based on prev. logic
  #######################################################################

  disks_by_id.each do |disk_id, disk_dev|
    Facter.add("disk_#{disk_id}_dev") do
      setcode do
        disk_dev
      end
    end
  end


  vxvm_disks_by_id.each do |disk_id, disk_dev|
    Facter.add("wxvm_disk_#{disk_id}_dev") do
      setcode do
        disk_dev
      end
    end
  end


  disks_wmp_by_id.each do |disk_id, disk_dev|
    Facter.add("disk_wmp_#{disk_id}_dev") do
      setcode do
        disk_dev
      end
    end

    #######################################################################
    # create new facts that map a disk name to a disk path
    # path depends on a type of a multipather available
    # ex.:
    # for disk: sda, we would either get /dev/sda or /dev/vx/dmp/sda path
    # so the fact may look like these:
    #   disk_sda => /dev/vx/dmp/vmdk0_0
    #   disk_sda1 => /dev/vx/dmp/vmdk0_0s1
    #   disk_sda2 => /dev/vx/dmp/vmdk0_0s2
    #
    #   disk_sda => /dev/sda
    #   disk_sda1 => /dev/sda1
    #   disk_sda2 => /dev/sda2
    #######################################################################

    disk_name = disk_dev.split("/")[-1]

    # query already existing facts using 'disk_id' of a disk
    # and build a new fact that is a mapping of a disk name to it's path

    Facter.add("disk_#{disk_name}") do
      setcode do
         Facter.value(:"disk_#{disk_id}_dev")
      end
    end
  end
end
