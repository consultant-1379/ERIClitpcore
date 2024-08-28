#!/bin/bash

rules=(
"-a always,exit -F path=/usr/bin/wall -F perm=x -F auid>=1000 -F auid!=4294967295 -k privileged"
"-a always,exit -F path=/usr/bin/passwd -F perm=x -F auid>=1000 -F auid!=4294967295 -k privileged"
"-a always,exit -F path=/usr/bin/chfn -F perm=x -F auid>=1000 -F auid!=4294967295 -k privileged"
"-a always,exit -F path=/usr/bin/chsh -F perm=x -F auid>=1000 -F auid!=4294967295 -k privileged"
"-a always,exit -F path=/usr/bin/su -F perm=x -F auid>=1000 -F auid!=4294967295 -k privileged"
"-a always,exit -F path=/usr/bin/chage -F perm=x -F auid>=1000 -F auid!=4294967295 -k privileged"
"-a always,exit -F path=/usr/bin/gpasswd -F perm=x -F auid>=1000 -F auid!=4294967295 -k privileged"
"-a always,exit -F path=/usr/bin/umount -F perm=x -F auid>=1000 -F auid!=4294967295 -k privileged"
"-a always,exit -F path=/usr/bin/newgrp -F perm=x -F auid>=1000 -F auid!=4294967295 -k privileged"
"-a always,exit -F path=/usr/bin/write -F perm=x -F auid>=1000 -F auid!=4294967295 -k privileged"
"-a always,exit -F path=/usr/bin/crontab -F perm=x -F auid>=1000 -F auid!=4294967295 -k privileged"
"-a always,exit -F path=/usr/bin/mount -F perm=x -F auid>=1000 -F auid!=4294967295 -k privileged"
"-a always,exit -F path=/usr/bin/pkexec -F perm=x -F auid>=1000 -F auid!=4294967295 -k privileged"
"-a always,exit -F path=/usr/bin/ssh-agent -F perm=x -F auid>=1000 -F auid!=4294967295 -k privileged"
"-a always,exit -F path=/usr/bin/at -F perm=x -F auid>=1000 -F auid!=4294967295 -k privileged"
"-a always,exit -F path=/usr/bin/sudo -F perm=x -F auid>=1000 -F auid!=4294967295 -k privileged"
"-a always,exit -F path=/usr/bin/screen -F perm=x -F auid>=1000 -F auid!=4294967295 -k privileged"
"-a always,exit -F path=/usr/sbin/pam_timestamp_check -F perm=x -F auid>=1000 -F auid!=4294967295 -k privileged"
"-a always,exit -F path=/usr/sbin/unix_chkpwd -F perm=x -F auid>=1000 -F auid!=4294967295 -k privileged"
"-a always,exit -F path=/usr/sbin/netreport -F perm=x -F auid>=1000 -F auid!=4294967295 -k privileged"
"-a always,exit -F path=/usr/sbin/userhelper -F perm=x -F auid>=1000 -F auid!=4294967295 -k privileged"
"-a always,exit -F path=/usr/sbin/usernetctl -F perm=x -F auid>=1000 -F auid!=4294967295 -k privileged"
"-a always,exit -F path=/usr/sbin/mount.nfs -F perm=x -F auid>=1000 -F auid!=4294967295 -k privileged"
"-a always,exit -F path=/usr/sbin/postdrop -F perm=x -F auid>=1000 -F auid!=4294967295 -k privileged"
"-a always,exit -F path=/usr/sbin/postqueue -F perm=x -F auid>=1000 -F auid!=4294967295 -k privileged"
"-a always,exit -F path=/usr/lib/polkit-1/polkit-agent-helper-1 -F perm=x -F auid>=1000 -F auid!=4294967295 -k privileged"
"-a always,exit -F path=/usr/lib64/vte-2.91/gnome-pty-helper -F perm=x -F auid>=1000 -F auid!=4294967295 -k privileged"
"-a always,exit -F path=/usr/libexec/utempter/utempter -F perm=x -F auid>=1000 -F auid!=4294967295 -k privileged"
"-a always,exit -F path=/usr/libexec/dbus-1/dbus-daemon-launch-helper -F perm=x -F auid>=1000 -F auid!=4294967295 -k privileged"
"-a always,exit -F path=/usr/libexec/openssh/ssh-keysign -F perm=x -F auid>=1000 -F auid!=4294967295 -k privileged"
"-a always,exit -F path=/usr/libexec/spice-gtk-x86_64/spice-client-glib-usb-acl-helper -F perm=x -F auid>=1000 -F auid!=4294967295 -k privileged"
"-a always,exit -F path=/usr/libexec/qemu-bridge-helper -F perm=x -F auid>=1000 -F auid!=4294967295 -k privileged"
"-a always,exit -F path=/ericsson/pib-scripts/etc/config.py -F perm=x -F auid>=1000 -F auid!=4294967295 -k privileged"
"-a always,exit -F path=/ericsson/pib-scripts/etc/healthcheck.py -F perm=x -F auid>=1000 -F auid!=4294967295 -k privileged"
"-a always,exit -F path=/ericsson/pib-scripts/etc/upgrade.py -F perm=x -F auid>=1000 -F auid!=4294967295 -k privileged"
"-a always,exit -F path=/ericsson/pib-scripts/etc/utilities.py -F perm=x -F auid>=1000 -F auid!=4294967295 -k privileged"
"-a always,exit -F path=/ericsson/pib-scripts/etc/utilities.pyo -F perm=x -F auid>=1000 -F auid!=4294967295 -k privileged"
"-a always,exit -F path=/ericsson/pib-scripts/etc/upgrade.pyc -F perm=x -F auid>=1000 -F auid!=4294967295 -k privileged"
"-a always,exit -F path=/ericsson/pib-scripts/etc/upgrade.pyo -F perm=x -F auid>=1000 -F auid!=4294967295 -k privileged"
"-a always,exit -F path=/ericsson/pib-scripts/etc/healthcheck.pyc -F perm=x -F auid>=1000 -F auid!=4294967295 -k privileged"
"-a always,exit -F path=/ericsson/pib-scripts/etc/healthcheck.pyo -F perm=x -F auid>=1000 -F auid!=4294967295 -k privileged"
"-a always,exit -F path=/ericsson/pib-scripts/etc/config.pyc -F perm=x -F auid>=1000 -F auid!=4294967295 -k privileged"
"-a always,exit -F path=/ericsson/pib-scripts/etc/config.pyo -F perm=x -F auid>=1000 -F auid!=4294967295 -k privileged"
"-a always,exit -F path=/ericsson/pib-scripts/etc/utilities.pyc -F perm=x -F auid>=1000 -F auid!=4294967295 -k privileged"
)

touch /etc/audit/rules.d/privileged.rules

for rule in "${rules[@]}"; do
    filepath=$(echo "$rule" | awk -F 'path=' '{print $2}' | awk '{print $1}')
    if ! grep -Fq "path=$filepath" /etc/audit/rules.d/privileged.rules; then
        echo "$rule" >> /etc/audit/rules.d/privileged.rules
    fi
done

awk '!seen[$0]++' /etc/audit/rules.d/privileged.rules > /etc/audit/rules.d/temp.rules && mv /etc/audit/rules.d/temp.rules /etc/audit/rules.d/privileged.rules

while IFS= read -r line; do
    filepath=$(echo "$line" | awk -F 'path=' '{print $2}' | awk '{print $1}')
    if [ ! -f "$filepath" ]; then
        continue
    fi
    echo "$line" >> /etc/audit/rules.d/filtered.rules
done < /etc/audit/rules.d/privileged.rules

if [ -f /etc/audit/rules.d/filtered.rules ]; then
    mv /etc/audit/rules.d/filtered.rules /etc/audit/rules.d/privileged.rules
else
    > /etc/audit/rules.d/privileged.rules
fi

/sbin/auditctl -R /etc/audit/rules.d/audit.rules
/sbin/auditctl -R /etc/audit/rules.d/privileged.rules
