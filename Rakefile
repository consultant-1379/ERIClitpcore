require 'rspec/core/rake_task'

RSpec::Core::RakeTask.new(:prepare) do |t|
  directory = `pwd`.strip
  sh "mkdir -p #{directory}/mcollective"
  sh "ln -s  #{directory}/puppet/mcollective_agents/files #{directory}/mcollective/agent"
  sh "ln -s  #{directory}/puppet/mcollective_utils/files #{directory}/mcollective/util"
end

RSpec::Core::RakeTask.new(:test) do |t|
  t.pattern = FileList['spec/test/agent/test*.rb']
  t.rspec_opts = "--color"
end

Kernel.trap("EXIT") do
  directory = `pwd`.strip
  sh "rm -rf #{directory}/mcollective"
end

task :default => [:prepare, :test]
