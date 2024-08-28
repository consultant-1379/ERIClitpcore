#!/bin/bash

#This script is run by the post-transaction-actions plugin on installation of package.
#It searches the files in the installed packages for executables which have the setgid
#and setuid bits set. If it finds any, it creates rules for those executables

PACKAGE=$1

for file in $(rpm -ql "$PACKAGE"); do
  if [ -f "$file" ]; then

    if find "$file" \( -perm -4000 -o -perm -2000 \) -type f -print | grep -q "$file"; then
      RULE="-a always,exit -F path=$file -F perm=x -F auid>=1000 -F auid!=4294967295 -k privileged"

      if ! grep "$RULE" /etc/audit/rules.d/privileged.rules; then
        echo "$RULE" >> /etc/audit/rules.d/privileged.rules
      fi
    fi
  fi
done

/sbin/auditctl -R /etc/audit/rules.d/audit.rules
/sbin/auditctl -R /etc/audit/rules.d/privileged.rules
/sbin/auditctl -R /etc/audit/rules.d/40-litp.rules
