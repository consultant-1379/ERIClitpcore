metadata    :name        => "puppetcerts",
            :description => "Cleans Puppet certificates",
            :author      => "Ericsson AB",
            :license     => "Ericsson",
            :version     => "0.1",
            :url         => "http://ericsson.com",
            :timeout     => 30

action "clean_all_certs", :description => "Performs puppet cert clean --all" do
    display :always

    output :out,
           :description => "Human readable status message",
           :display_as  => "Result"
end

action "clean_cert", :description => "Performs puppet cert clean for one certificate" do
    display :always

    input  :node,
           :prompt => "Node",
           :description => "Node for which certificates will be cleaned",
           :type => :string,
           :validation  => '.*',
           :optional    => false,
           :maxlength   => 128

    output :out,
           :description => "Human readable status message",
           :display_as  => "Result"
end

action "list_certs", :description => "Lists all nodes with puppet certs" do
    display :always

    output :out,
           :description => "Human readable status message",
           :display_as  => "Result"

    output :nodes,
           :description => "List of nodes with certificates",
           :display_as  => "Nodes"
end

