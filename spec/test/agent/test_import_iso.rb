#!/usr/bin/env ruby

require File.join([File.dirname(__FILE__), '/../../spec_helper'])

describe "util test" do

  before(:all) do
    @agent = MCollective::Test::LocalAgentTest.new("importiso", :config => {:libdir => "../../../../"}).plugin
  end

  describe "#create_snapshot" do
     it "should have valid metadata" do
       @agent.expects(:run).returns(0)
       result = @agent.call(:verify_checksum, {:image_filename => "/tmp/my_image.qcow2", :directory => "/vg/lg1"})
       result.should be_successful
       expect(result).to eq({:data=>{:status=>0}, :statusmsg=>"OK", :statuscode=>0})
     end
  end
end