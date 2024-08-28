module MCollective
  module Agent
    class Core<RPC::Agent
      include MCollective::RPC
      begin
        PluginManager.loadclass("MCollective::Util::LogAction")
        log_action = Util::LogAction
      rescue LoadError => e
        raise "Cannot load logaction util: %s" % [e.to_s]
      end
      begin
        PluginManager.loadclass("MCollective::Util::CoreUtils")
        cu = Util::CoreUtils
      rescue LoadError => e
        raise "Cannot load core utils util: %s" % [e.to_s]
      end

      action "reboot" do
          cmd = "(sleep 1; /sbin/shutdown -r now)&"
          reply[:status] = run("#{cmd}",
                               :stdout => :out,
                               :stderr => :err,
                               :chomp => true)
      end

      action "reboot_force" do
          cmd = "(sleep 1; reboot -f)&"
          reply[:status] = run("#{cmd}",
                               :stdout => :out,
                               :stderr => :err,
                               :chomp => true)
      end

      action "has_rebooted_uptime" do
          time_ms = Float(request[:reboot_time_elapsed])
          # we need the system uptime only
          cmd = "cat /proc/uptime | awk '{print $1}'"
          reply[:status] = run("#{cmd}",
                               :stdout => :out,
                               :stderr => :err,
                               :chomp => true)
          if reply[:status] != 0
            # error getting uptime
            reply[:status] = 2
            return reply
          end
          local_uptime = Float(reply[:out])
          log_action.log("has_rebooted_uptime", "Time since reboot: #{time_ms}")
          log_action.log("has_rebooted_uptime", "System uptime: #{local_uptime}")
          if local_uptime < time_ms
            reply[:status] = 0
            reply[:out] = ''
            log_action.log("has_rebooted_uptime", "Uptime is less than reboot time, node has rebooted successfully")
          else
            reply[:status] = 1
            reply[:out] = ''
            log_action.log("has_rebooted_uptime", "Uptime is greater than reboot time, node has not rebooted yet")
          end
      end

      action "safe_stop_puppet" do
          timeout = 0
          while cu.puppet_applying?() do
              # 30 minutes
              if timeout >= 1800
                  reply[:retcode] = 1
                  reply[:out] = 'Puppet run did not finish on time'
                  reply[:err] = 'Puppet run did not finish on time'
                  return reply
              end
              if timeout % 5 == 0
                  log_action.log("safe_stop_puppet", "Puppet is applying a catalog, cannot stop the service yet")
              end
              sleep(1)
              timeout += 1
          end
          cmd = "sed 's/Red Hat Enterprise Linux Server release //' /etc/redhat-release | awk -F '.' '{print $1}'"
          rhel_ver_hash = {:out => "", :err => ""}
          rhel_ver_hash[:status] = run("#{cmd}",
                                       :stdout => rhel_ver_hash[:out],
                                       :stderr => rhel_ver_hash[:err],
                                       :chomp => true)
          if rhel_ver_hash[:status] == 0 and rhel_ver_hash[:out].to_i >= 7
              cmd = "systemctl stop puppet.service"
          else
              cmd = "service puppet stop"
          end

          reply[:status] = run("#{cmd}",
                               :stdout => :out,
                               :stderr => :err,
                               :chomp => true)
          return reply
      end

      action "set_chkconfig" do
          cmd = "chkconfig #{request[:service_name]} #{request[:enable]}"
          reply[:status] = run("#{cmd}",
                               :stdout => :out,
                               :stderr => :err,
                               :chomp => true)
      end
    end
  end
end
