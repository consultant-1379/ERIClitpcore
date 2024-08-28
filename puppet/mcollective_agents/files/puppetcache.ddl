metadata :name        => "puppetcache",
         :description => "Actions related to puppet caching",
         :author      => "Ericsson AB",
         :license     => "Ericsson",
         :version     => "1.0",
         :url         => "http://ericsson.com",
         :timeout     => 1800

action "clean", :description => "Issues a curl command to invalidate the puppet production cache" do
    display :always

    output :out,
           :description => "String output from the curl command",
           :display_as => "out"

    output :status,
           :description => "Integer result from the action, 0 indicating success, non zero error",
           :display_as => "status"

    output :err,
           :description => "Error message if an error occurred.",
           :display_as => "err"
end
