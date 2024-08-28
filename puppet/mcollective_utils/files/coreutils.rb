module MCollective
    module Util
        class CoreUtils

            def self.puppet_agent_lock_file()
              lock_file_path = Puppet[:agent_catalog_run_lockfile]
              return lock_file_path
            end

            def self.puppet_applying?()
              return false unless File.exist?(puppet_agent_lock_file)

              if File::Stat.new(puppet_agent_lock_file).size > 0
                return is_puppet_agent_applying?(File.read(puppet_agent_lock_file))
              end
              #Used to cover the case where the Puppet agent can leave behind
              #an empty lockfile.
              return false
            end

            def self.is_puppet_agent_applying?(pid)
              File.read("/proc/#{pid}/cmdline").include? "puppet" rescue false
            end
        end
    end
end
