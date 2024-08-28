metadata :name        => "importiso",
         :description => "Agent to handle import iso",
         :author      => "Ericsson AB",
         :license     => "Ericsson",
         :version     => "1.0",
         :url         => "http://ericsson.com",
         :timeout     => 1000

action "rsync_images", :description => "Importing packages from source to destination directory" do

    display :always

    input :source_path,
          :prompt      => "Source Path",
          :description => "Source Path where ISO is mounted",
          :type        => :string,
          :validation  => '.*',
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

action "verify_checksum", :description => "Verify md5 checksum" do

    display :always

    input :image_filename,
          :prompt      => "Image file",
          :description => "Image file",
          :type        => :string,
          :validation  => '.*',
          :optional    => false,
          :maxlength   => 500
    input :directory,
          :prompt      => "Directory",
          :description => "Directory containing image and checksum files",
          :type        => :string,
          :validation  => '^(/)?([^/\0]+(/)?)+$',
          :optional    => false,
          :maxlength   => 500

    output :status,
           :description => "The output of the command",
           :display_as  => "Command result",
           :default     => "no output"
    summarize do
      aggregate summary(:status)
    end
end

action "generate_checksum", :description => "Generate md5 checksum of an image" do

    display :always

    input :image_filepath,
          :prompt      => "Image file",
          :description => "Image file",
          :type        => :string,
          :validation  => '.*',
          :optional    => false,
          :maxlength   => 500

    input :destination_path,
          :prompt      => "Destination Path",
          :description => "Destination Path",
          :type        => :string,
          :validation  => '^(/)?([^/\0]+(/)?)+$',
          :optional    => false,
          :maxlength   => 500

    output :status,
           :description => "The output of the command",
           :display_as  => "Command result",
           :default     => "no output"
    summarize do
      aggregate summary(:status)
    end
end
