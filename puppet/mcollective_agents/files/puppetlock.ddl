metadata    :name        => "puppetlock",
            :description => "Cleans stale puppet agent lock files",
            :author      => "Ericsson AB",
            :license     => "Ericsson",
            :version     => "1.0",
            :url         => "http://ericsson.com",
            :timeout     => 20

action "clean", :description => "Cleans stale puppet agent lock files" do
    display :always

    output :retcode,
           :description => "The exit code from cleaning puppet agent lock file",
           :display_as => "Result code"

    output :out,
           :description => "The stdout from cleaning puppet agent lock file",
           :display_as => "out"

    output :err,
           :description => "The stderr from cleaning puppet agent lock file",
           :display_as => "err"

end

action "is_running", :description => "Checks if Puppet is running a catalog" do
    display :always

    output :is_running,
           :description => "boolean saying whether Puppet is applying a catalog",
           :display_as => "Result"
end