metadata :name        => "core",
         :description => "Core actions needed by several plugins",
         :author      => "Ericsson AB",
         :license     => "Ericsson",
         :version     => "1.0",
         :url         => "http://ericsson.com",
         :timeout     => 1800

action "reboot", :description => "Reboot node" do
    display :always

    output :status,
           :description => "The output of the command",
           :display_as  => "Command result",
           :default     => "no output"
end

action "reboot_force", :description => "Reboot node with -f flag" do
    display :always

    output :status,
           :description => "The output of the command",
           :display_as  => "Command result",
           :default     => "no output"
end

action "has_rebooted_uptime", :description => "Check node has rebooted" do
    display :always

    input :reboot_time_elapsed,
          :prompt      => "Reboot time elapsed",
          :description => "Time elapsed on the MS since the reboot was first issued",
          :type        => :string,
          :validation  => '^[\d+\.]+$',
          :optional    => false,
          :maxlength   => 90

    output :status,
           :description => "The output of the command",
           :display_as  => "Command result",
           :default     => "no output"
end

action "safe_stop_puppet", :description => "Stop Puppet service when no catalog is being applied" do
    display :always

    output :status,
           :description => "The output of the command",
           :display_as  => "Command result",
           :default     => "no output"
end

action "set_chkconfig", :description => "Set chkconfig on a service" do
    display :always

    input :enable,
          :prompt      => "on or off",
          :description => "Enable or disable chkconfig",
          :type        => :string,
          :validation  => '^on|off$',
          :optional    => false,
          :maxlength   => 3

    input :service_name,
          :prompt      => "Name of the service",
          :description => "Service to run chkconfig on",
          :type        => :string,
          :validation  => '^[a-zA-Z\-_\d]+$',
          :optional    => false,
          :maxlength   => 50

    output :status,
           :description => "The output of the command",
           :display_as  => "Command result",
           :default     => "no output"
end