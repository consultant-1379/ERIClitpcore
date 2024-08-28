
module MCollective
  module Agent
    class Puppetcache <RPC::Agent
      begin
        PluginManager.loadclass("MCollective::Util::LogAction")
        log_action = Util::LogAction
      rescue LoadError => e
        raise "Cannot load logaction util: %s" % [e.to_s]
      end

      action "clean" do
          cmd = "puppet config print hostcert hostprivkey cacert server " \
                "masterport environment --log_level=notice"
          log_action.log("puppetcache_clean", "Issuing command: \"#{cmd}\"")
          reply[:status] = run("#{cmd}",
                               :stdout => :out,
                               :stderr => :err,
                               :chomp => true)
          if reply[:status] != 0
            log_action.log("puppetcache_clean", "Command: \"#{cmd}\" failed. " \
                           "Status: #{reply[:status]}, error: #{reply[:err]}")
            return reply
          end

          puppet_params = Hash[reply[:out].each_line.map {|line| line.strip().split(' = ')}]
          cmd = "curl -sSi --cert #{puppet_params["hostcert"]} " \
                "--key #{puppet_params["hostprivkey"]} " \
                "--cacert #{puppet_params["cacert"]} -X DELETE " \
                "https://#{puppet_params["server"]}:#{puppet_params["masterport"]}/" \
                "puppet-admin-api/v1/environment-cache?environment=#{puppet_params["environment"]}"

          tries = 15
          sleep_duration = 6
          counter = 1

          tries.times do
              log_action.log("puppetcache_clean", "Issuing command to clean puppet cache (#{counter}/#{tries}): \"#{cmd}\"")
              reply[:status] = run("#{cmd}",
                                   :stdout => :out,
                                   :stderr => :err,
                                   :chomp => true)

              if reply[:status] == 0
                http_response = reply[:out].lines.first.strip()
                if http_response != "HTTP/1.1 204 No Content"
                  reply[:status] = http_response.split(' ')[1]
                  reply[:err] = http_response
                  log_action.log("puppetcache_clean", "Clean puppet cache failed. " \
                                 "Unexpected http response: #{reply[:err]}")
                end
                break
              else
                log_action.log("puppetcache_clean", "Command to clean puppet cache failed. " \
                               "Status: #{reply[:status]}, error: #{reply[:err]}")
                sleep sleep_duration
                counter += 1
              end
          end
          return reply
      end
    end
  end
end


