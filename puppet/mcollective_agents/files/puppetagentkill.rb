module MCollective
  module Agent
    class Puppetagentkill < RPC::Agent
      begin
        PluginManager.loadclass("MCollective::Util::CoreUtils")
        cu = Util::CoreUtils
      rescue LoadError => e
        raise "Cannot load core utils util: %s" % [e.to_s]
      end

      action "kill_puppet_agent" do
        msg = "Puppet agent not applying"
        status = 0
        i = 0

        begin
          while cu.puppet_applying?() and i <= 2  do
            pid = Integer(File.read(cu.puppet_agent_lock_file))
            case i
            when 0
              Process.kill("TERM", pid)
              msg = "Sent signal TERM to puppet agent with pid: #{pid}"
              sleep 4
            when 1
              Process.kill("KILL", pid)
              msg = "Sent signal KILL to puppet agent with pid: #{pid}"
              sleep 4
            when 2
              msg = "Failed to terminate puppet agent with pid: #{pid}"
              status=1
            end
            i +=1
          end
        rescue Errno::ENOENT, Errno::ESRCH
        end

        reply[:status] = status
        reply[:out] = msg
        reply[:err] = ""

        return reply
      end
    end
  end
end