require 'syslog'
require 'shellwords'

module MCollective
  module Agent
    class Importiso<RPC::Agent
      def log(log_name, *args)
        Syslog.open(log_name)
        Syslog.log(Syslog::LOG_INFO, *args)
        Syslog.close()
      end

      def debug(log_name, *args)
        Syslog.open(log_name)
        Syslog.log(Syslog::LOG_DEBUG, *args)
        Syslog.close()
      end

      action "rsync_images" do
        cmd = "rsync -rtd --chmod=Du=rwx,Dgo=rx,Fu=rw,Fgo=r #{request[:source_path].shellescape}/images/ /var/www/html/images --exclude '*/*/*/'"
        self.debug("rsync_images", "%s", cmd)
        reply[:status] = run("#{cmd}",
                              :stdout => :out,
                              :stderr => :err,
                              :chomp => true)
      end
      action "verify_checksum" do
        cmd = "md5sum -b #{request[:directory].shellescape}/#{request[:image_filename].shellescape} | awk -F' ' '{print $1}' | diff --ignore-all-space - #{request[:directory].shellescape}/#{request[:image_filename].shellescape}.md5 1>&2"
        self.debug("verify_checksum", "%s", cmd)
        cmd << " || (echo File #{request[:image_filename].shellescape} failed checksum test 1>&2 && exit 1)"
        reply[:status] = run("#{cmd}",
                              :stdout => :out,
                              :stderr => :err,
                              :chomp => true)
      end
      action "generate_checksum" do
        cmd = "md5sum #{request[:image_filepath].shellescape} | awk -F' ' '{print $1}' > #{request[:destination_path].shellescape}/$(basename #{request[:image_filepath].shellescape}).md5"
        self.debug("generate_checksum", "%s", cmd)
        reply[:status] = run("#{cmd}",
                              :stdout => :out,
                              :stderr => :err,
                              :chomp => true)
      end
    end
  end
end
