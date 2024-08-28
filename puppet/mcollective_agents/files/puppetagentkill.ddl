metadata    :name        => "puppetagentkill",
            :description => "Kills the applying puppet agent",
            :author      => "Ericsson AB",
            :license     => "Ericsson",
            :version     => "1.0",
            :url         => "http://ericsson.com",
            :timeout     => 60

action "kill_puppet_agent", :description => "Kills the puppet agent process if it is applying a catalog" do
    display :always

    output :out,
           :description => "A string indicating if the puppet agent was not applying or killed",
           :display_as => "out"

    output :status,
           :description => "Integer result from the action, 0 indicating success",
           :display_as => "status"

    output :err,
           :description => "Error message if an error occurred.",
           :display_as => "err"
end
