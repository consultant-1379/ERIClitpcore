module MCollective
  module Agent
    class Puppetlock < RPC::Agent
      begin
        PluginManager.loadclass("MCollective::Util::CoreUtils")
        cu = Util::CoreUtils
      rescue LoadError => e
        raise "Cannot load core utils util: %s" % [e.to_s]
      end

      action 'clean' do
        puppet_agent_lock_file = cu.puppet_agent_lock_file
        puppet_applying = cu.puppet_applying?()
        lock_file_exists = File.exist?(puppet_agent_lock_file)

        if lock_file_exists and !puppet_applying
          reply[:retcode] = run("rm -vf %s" % [puppet_agent_lock_file],
                                :stdout => :out,
                                :stderr => :err,
                                :chomp => true)
        else
          reply[:retcode] = 0
          reply[:out] = 'No puppet agent lock file to remove'
          reply[:err] = ''
        end
      end

      action 'is_running' do
        reply[:is_running] = cu.puppet_applying?()
      end
    end
  end
end
