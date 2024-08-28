require 'syslog'

module MCollective
  module Agent
    class Packagesimport<RPC::Agent
      def log(log_name, msg)
        Syslog.open(log_name)
        Syslog.log(Syslog::LOG_INFO, msg)
        Syslog.close()
      end

      action "rsync_packages" do
        appstream = "#{request[:import_appstream]}"
        cmd_prefix = "rsync -rtd --chmod=Du=rwx,Dgo=rx,Fu=rw,Fgo=r --include=\"*.rpm\" --include=\""
        if appstream == "True"
          cmd = cmd_prefix + "*modules.yaml.gz\" "
        else
          cmd = cmd_prefix + "comps.xml\" --exclude=\"*\" "
        end
        cmd << "#{request[:source_path]}  #{request[:destination_path]} "

        self.log("import_agent", cmd)
        reply[:status] = run("#{cmd}",
                              :stdout => :out,
                              :stderr => :err,
                              :chomp => true)

      end
      action "create_repo" do
        cmd = "createrepo -C #{request[:destination_path]}"
        groupfile_path = "#{request[:destination_path]}/comps.xml"
        if File.exists?(groupfile_path)
          cmd += " -g #{groupfile_path}"
        end
        self.log("import_agent", cmd)
        reply[:status] = run("#{cmd}",
                              :stdout => :out,
                              :stderr => :err,
                              :chomp => true)

      end
      action "clean_yum_cache" do
        cmd = "yum clean all"
        self.log("import_agent", cmd)
        reply[:status] = run("#{cmd}",
                              :stdout => :out,
                              :stderr => :err,
                              :chomp => true)

      end
      action "save_version_file" do
        cmd = "cp #{request[:source_path]} #{request[:destination_path]} "
        self.log("import_agent", cmd)
        reply[:status] = run("#{cmd}",
                              :stdout => :out,
                              :stderr => :err,
                              :chomp => true)

      end
    end
  end
end

