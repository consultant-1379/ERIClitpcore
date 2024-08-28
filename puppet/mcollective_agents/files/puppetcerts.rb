module MCollective
  module Agent
    class Puppetcerts < RPC::Agent
      @@puppet_cert_cmd="puppet cert"
      @@puppet_cert_clean_cmd="#{@@puppet_cert_cmd} clean"
      @@log_level="--log_level=notice"
      @@colour="--color=none"
      @@all_options="--all #{@@colour} #{@@log_level}"

      action 'clean_all_certs' do
        cmd="#{@@puppet_cert_clean_cmd} #{@@all_options}"
        out = ""
        err = ""
        reply[:status] = run("#{cmd}",
                             :stdout => :out,
                             :stderr => :err,
                             :chomp => true)
      end

      action 'clean_cert' do
        out = ""
        err = ""
        node = request[:node]
        if node == ""
          raise "No node specified"
        end
        cmd="#{@@puppet_cert_clean_cmd} #{node} #{@@colour} #{@@log_level}"
        reply[:status] = run("#{cmd}",
                             :stdout => :out,
                             :stderr => :err,
                             :chomp => true)
      end

      action 'list_certs' do
        out = ""
        err = ""
        cmd="#{@@puppet_cert_cmd} list #{@@all_options}"
        reply[:status] = run("#{cmd}",
                             :stdout => :out,
                             :stderr => :err,
                             :chomp => true)
        node_list = []
        for l in reply[:out].each_line
          node_list << '%s' % (l.split(' ')[1].gsub('"',''));
        end
        reply[:nodes] = node_list * ":"

      end

    end

  end
end
