metadata :name        => "packagesimport",
         :description => "Agent to handle import iso",
         :author      => "Ericsson AB",
         :license     => "Ericsson",
         :version     => "1.0",
         :url         => "http://ericsson.com",
         :timeout     => 1000

action "rsync_packages", :description => "Importing packages from source to destination directory" do

    display :always

    input :source_path,
          :prompt      => "Source Path",
          :description => "Source Path",
          :type        => :string,
          :validation  => '^(/)?([^/\0]+(/)?)+$',
          :optional    => false,
          :maxlength   => 300

    input :destination_path,
          :prompt      => "Destination Path",
          :description => "The size of the snapshot plus its unit",
          :type        => :string,
          :validation  => '^(/)?([^/\0]+(/)?)+$',
          :optional    => false,
          :maxlength   => 300

    output :status,
           :description => "The output of the command",
           :display_as  => "Command result",
           :default     => "no output"
    summarize do
      aggregate summary(:status)
    end
end
action "create_repo", :description => "Create repo in specified directory" do
    display :always

    input :destination_path,
          :prompt      => "Path",
          :description => "Path",
          :type        => :string,
          :validation  => '^(/)?([^/\0]+(/)?)+$',
          :optional    => false,
          :maxlength   => 300
end
action "clean_yum_cache", :description => "Clear yum cache" do

    display :always

    output :status,
           :description => "The output of the command",
           :display_as  => "Command result",
           :default     => "no output"
    summarize do
      aggregate summary(:status)
    end
end

action "save_version_file", :description => "Preserve version file" do
    display :always

    input :destination_path,
          :prompt      => "Source path",
          :description => "Path to copy from",
          :type        => :string,
          :validation  => '^(/)?([^/\0]+(/)?)+$',
          :optional    => false,
          :maxlength   => 300

    input :destination_path,
          :prompt      => "Target path",
          :description => "Path to copy to",
          :type        => :string,
          :validation  => '^(/)?([^/\0]+(/)?)+$',
          :optional    => false,
          :maxlength   => 300
end
