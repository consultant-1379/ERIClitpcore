function enable_ip_tables {
    for port in "$@"; do
        iptables -L -n | grep "$port" > /dev/null || iptables -I INPUT -m state --state NEW -m tcp -p tcp --dport "$port" -j ACCEPT
    done
}

function generate_puppet_cert {
    puppet cert --generate "$hostname"
    if [[ -f /usr/sbin/puppetdb ]]; then
        /usr/sbin/puppetdb ssl-setup
    fi
}

function enable_history_timestamp {
    grep_bashrc="$(grep -i 'HIST' ~/.bashrc)"
    if [ -z "$grep_bashrc" ]
    then
        cat << EOM >> ~/.bashrc
export HISTSIZE=
export HISTSIZELIMIT=
export HISTTIMEFORMAT="[%d-%m-%y %T] "
shopt -s histappend
PROMPT_COMMAND="history -a";\$PROMPT_COMMAND
EOM
    fi
    source ~/.bashrc
}

function add_audit_rule {

    AUDIT_RULES='/etc/audit/audit.rules'
    LITP_AUDIT_RULES='/etc/audit/rules.d/40-litp.rules'
    NEW_RULE='-a always,exit -F arch=b64 -S mount -S umount2 -k mount_umount'

    #Add new LITP specific audit rule file.
    [ -f $AUDIT_RULES ] && grep -qxF -- "${NEW_RULE}" "${AUDIT_RULES}" && return

    #Adds rule to audit.rules if it doesn't already exist.
    echo "${NEW_RULE}" > "${LITP_AUDIT_RULES}"
    echo "${NEW_RULE}" >> "${AUDIT_RULES}"
    auditctl -R "${LITP_AUDIT_RULES}"

}

function filter_cached_catalog() {
    filter_catalog="/tmp/filter_cached_catalog.py"
    cat <<EOF > "${filter_catalog}"
import json, sys, os
dir_path = '/var/lib/puppet/client_data/catalog/'
catalogs = [f for f in os.listdir(dir_path) if f.endswith('.json')]
if len(catalogs) != 1:
    print "Expected one cached catalog, found the following: %s" % catalogs
    sys.exit(1)
catalog = dir_path + catalogs[0]
if not os.path.exists(catalog) or not os.path.isfile(catalog) or not os.access(catalog, os.R_OK | os.W_OK):
    print "Catalog %s not found" % catalog
    sys.exit(1)
passenger = 'passenger'
litp_passenger = "litp::%s" % passenger
litp_passenger_title = litp_passenger.title()
litp_passenger_class = "Class[%s]" % litp_passenger_title
httpd = 'httpd'
litp_httpd = "litp::%s" % httpd
litp_httpd_title = litp_httpd.title()
litp_httpd_class = "Class[%s]" % litp_httpd_title
puppet_dir = "/opt/ericsson/nms/litp/etc/puppet"
passenger_pp = "%s/modules/litp/manifests/%s.pp" % (puppet_dir, passenger)
httpd_pp = "%s/modules/litp/manifests/httpd.pp" % puppet_dir
site_pp = "%s/manifests/plugins/site.pp" % puppet_dir
json_data = None
with open(catalog, 'r') as fd:
    json_data = json.load(fd)
    if 'data' in json_data.keys():
        if 'classes' in json_data['data'].keys():
            json_data['data']['classes'] = [klass for klass in json_data['data']['classes']
                                            if not klass == litp_passenger]
            json_data['data']['classes'].append(litp_httpd)
        if 'edges' in json_data['data'].keys():
            for edge in json_data['data']['edges']:
                if edge['source'] == 'Stage[main]' and edge['target'] == litp_passenger_class:
                   edge['target'] = litp_httpd_class
                if edge['source'] == litp_passenger_class and \\
                   any(edge['target'] == x
                       for x in ("Service[%s]" % httpd,
                                 "Package[%s]" % httpd,
                                 'File_line[poodle_protection]')):
                    edge['source'] = litp_httpd_class
            json_data['data']['edges'] = [edge for edge in json_data['data']['edges']
                                          if not any(edge[k] == litp_passenger_class
                                                     for k in ('source', 'target')) and \\
                                             not edge['target'] == "File[%s]" % site_pp]
        if 'resources' in json_data['data'].keys():
            for resource in json_data['data']['resources']:
               if resource['title'] == litp_passenger_title:
                   resource['title'] = litp_httpd_title
               if resource['title'] == litp_httpd_title or \\
                  (resource['title'] == httpd and resource['type'] in ('Package', 'Service')) or \\
                  (resource['title'] == "poodle_protection" and resource['type'] == 'File_line'):
                   if resource['title'] != litp_httpd_title:
                       resource['file'] = httpd_pp
                       resource['tags'].extend([litp_httpd, httpd])
                   resource['tags'] = [tag for tag in resource['tags'] if not tag in (passenger, litp_passenger)]
            json_data['data']['resources'] = [resource for resource in json_data['data']['resources'] if not (
                   ('tags' in resource.keys() and any(resource['tags'] == tag for tag in (litp_passenger, passenger)) ) or \\
                   ('title' in resource.keys() and (resource['title'] == litp_passenger_title or resource['title'] == site_pp)) or \\
                   ('file' in resource.keys() and resource['file'] == passenger_pp))]
        if 'tags' in json_data['data'].keys():
            json_data['data']['tags'] = [tag for tag in json_data['data']['tags']
                                         if tag not in (litp_passenger, passenger)]
            json_data['data']['tags'].extend([litp_httpd, httpd])
if json_data:
    with open(catalog, 'w') as fd:
        json.dump(json_data, fd, separators=(',', ':'))
EOF
    python "${filter_catalog}"
    rm -f "${filter_catalog}"
}

add_audit_rule
hostname_orig=$(hostname)
postgres_port=$(grep "\$port *=" /opt/ericsson/nms/litp/etc/puppet/modules/postgresql_litp/manifests/params.pp | awk '{print $NF}')
sed -ie "s/\(^pg_hostname = \){hostname}$/\1'${hostname_orig}'/" /etc/litpd.conf
sed -ie "s/\(^pg_port = \){port}$/\1'${postgres_port}'/" /etc/litpd.conf
hostname=${hostname_orig,,}
sed -i "s/#ServerName www.example.com:80/ServerName ${hostname}:80/g" /etc/httpd/conf/httpd.conf

# Only perform the operations in this script when installing
# $1 == "1" means its installation %post
if [ "$1" == "1" ]; then
    enable_history_timestamp
    # Setup python path
    SITE=$(python -c "from distutils.sysconfig import get_python_lib; print(get_python_lib())")
    echo "/opt/ericsson/nms/litp/lib" > "${SITE}/litp.pth"
    for svc in httpd tftp cobblerd puppet; do chkconfig ${svc} on; done
    # Update the iptables for MS:9999, litp service, see if it already exists
    systemctl restart iptables.service
    iptables -L INPUT -n | grep dpt:9999
    if [ $? == 0 ]; then
        iptables -D INPUT -p tcp -m state --state NEW -m tcp --dport 9999 -j ACCEPT
    fi
    iptables -I INPUT -p tcp -m state --state NEW -m tcp --dport 9999 -j ACCEPT
    /sbin/service iptables save
    mkdir -p /var/log/litp
    chmod 740 /var/log/litp
    setfacl -Rm u:litp-admin:r /var/log/litp
    chmod +x /usr/local/bin/litpd.sh
    chmod +x /opt/ericsson/nms/litp/bin/litp_service.py
    systemctl enable litpd.service
    mkdir -p /opt/ericsson/nms/litp/etc/puppet/manifests/plugins
    mkdir -p /opt/ericsson/nms/litp/keyset
    # Generate puppet conf files from templates
    sed -e "s/{hostname}/$hostname/g" /opt/ericsson/nms/litp/etc/puppet/puppet.conf > /etc/puppet/puppet.conf
    sed -e "s/{hostname}/$hostname/g" /opt/ericsson/nms/litp/etc/sysconfig/puppet > /etc/sysconfig/puppet
    touch /opt/ericsson/nms/litp/etc/puppet/litp_config_version
    # Generate puppet default manifests from templates
    if [ "$1" = "1" ]; then
        sed -e "s/{hostname}/$hostname/g" /opt/ericsson/nms/litp/etc/puppet/modules/litp/default_manifests/ms1.pp > "/opt/ericsson/nms/litp/etc/puppet/manifests/plugins/${hostname}.pp"
    fi
    chcon -R -u system_u /opt/ericsson/nms/litp/etc/puppet/manifests/plugins
    echo "allow *" >> /etc/puppet/auth.conf
    echo "*" > /etc/puppet/autosign.conf
    touch /etc/puppet/namespaceauth.conf
    chmod 644 /etc/puppet/puppet.conf
    chmod 644 /etc/sysconfig/puppet
    chmod 664 /etc/litp_logging.conf
    chown root:litp-admin /etc/litp_logging.conf
    # Create empty litp_shadow file
    touch /opt/ericsson/nms/litp/etc/litp_shadow
    chmod 664 /opt/ericsson/nms/litp/etc/litp_shadow
    chown root:litp-admin /opt/ericsson/nms/litp/etc/litp_shadow

    if [ "$(crontab -u root -l | grep tmpwatch | wc -l)" -ne "0" ]; then
        crontab -u root -l | grep -v tmpwatch | crontab -u root -
    fi
    #Generate self-signed cert and key for the https server (cherrypy)
    SSL_DIR=/opt/ericsson/nms/litp/etc/ssl
    if [ ! -d ${SSL_DIR} ] ; then
       /bin/mkdir -p $SSL_DIR
    fi
    NUM_DAYS_IN_YEAR=365
    num_days=$(($NUM_DAYS_IN_YEAR*50))
    if [ ! -f $SSL_DIR/litp_server.key ] || [ ! -f $SSL_DIR/litp_server.cert ] ; then
       echo -e "XX\n\n \n \n\nlitpms.ericsson.se\n\n" | openssl req -new -x509 \
       -newkey rsa:2048 -keyout $SSL_DIR/litp_server.key -nodes -days $num_days \
       -out $SSL_DIR/litp_server.cert &> /dev/null
    fi
    setsebool -P httpd_can_network_connect on
    setsebool -P httpd_setrlimit on
    setsebool -P httpd_run_stickshift on
    setsebool -P rsync_export_all_ro on
    semodule -i /opt/ericsson/nms/litp/etc/selinux/domain.pp
    semodule -i /opt/ericsson/nms/litp/etc/selinux/openshift_initrc.pp
    semodule -i /opt/ericsson/nms/litp/etc/selinux/rsynclitp.pp
    semodule -i /opt/ericsson/nms/litp/etc/selinux/rabbitmq.pp > /dev/null 2>&1
    semanage permissive -a httpd_t
    semanage permissive -a cobblerd_t
    generate_puppet_cert
    for svc in httpd puppetserver puppetserver_monitor cobblerd; do systemctl status ${svc}.service 2> /dev/null && systemctl restart ${svc}.service || systemctl start ${svc}.service; done
    enable_ip_tables 4369 9100:9105 61614
    service iptables save
elif [ "$1" -ge 2 ]; then
    # This is the "upgrade" section
    enable_history_timestamp
    # Generate puppet conf files from templates
    sed -e "s/{hostname}/$hostname/g" /opt/ericsson/nms/litp/etc/puppet/puppet.conf > /etc/puppet/puppet.conf
    sed -e "s/{hostname}/$hostname/g" /opt/ericsson/nms/litp/etc/sysconfig/puppet > /etc/sysconfig/puppet
    touch /opt/ericsson/nms/litp/etc/puppet/litp_config_version
    # Change permisions to litpd service
    chmod +x /usr/local/bin/litpd.sh
    chmod +x /opt/ericsson/nms/litp/bin/litp_service.py
    semanage permissive -a httpd_t
    semanage permissive -a cobblerd_t
    setsebool -P rsync_export_all_ro on
    semodule -i /opt/ericsson/nms/litp/etc/selinux/rsynclitp.pp
    rm -f /etc/yum/pluginconf.d/versionlock.list.default
    [ -f /etc/yum/pluginconf.d/versionlock.list ] && /bin/sed -i '/EXTRlitp/d' /etc/yum/pluginconf.d/versionlock.list
    [ -f /etc/yum/pluginconf.d/versionlock.list ] && /bin/sed -i '/VRTS/d' /etc/yum/pluginconf.d/versionlock.list

    HTML_DIR='/var/www/html'
    OS_7_9_PATH="${HTML_DIR}/7.9"
    SYM_LINK_OS_7_PATH="${HTML_DIR}/7"
    X86_64_PACKAGES='x86_64/Packages'
    OS_REPO="${OS_7_9_PATH}/os/${X86_64_PACKAGES}"
    UPDATES_REPO="${OS_7_9_PATH}/updates/${X86_64_PACKAGES}"
    [ ! -d "${OS_7_9_PATH}" ] && mkdir -p "${OS_7_9_PATH}"
    [ ! -L "${SYM_LINK_OS_7_PATH}" ] && ln -s "${OS_7_9_PATH}" "${SYM_LINK_OS_7_PATH}"
    symlink_target=$(readlink "${SYM_LINK_OS_7_PATH}")
    if [[ "${symlink_target%/}" = "${OS_7_9_PATH%/}" ]]; then
        [[ -d "${OS_REPO}/repodata" ]] || (echo "checking ${OS_REPO}" && mkdir -p "${OS_REPO}/" && createrepo "${OS_REPO}" )
        [[ -d "${UPDATES_REPO}/repodata" ]] || (echo "checking ${UPDATES_REPO}" && mkdir -p "${UPDATES_REPO}/" && createrepo "${UPDATES_REPO}" )
    else
        echo "symlink ${SYM_LINK_OS_7_PATH} not set up correctly"
        exit 1
    fi
    # See LITPCDS-9288 - create plugins repo if we're upgrading and it's missing.
    PLUGINSREPO=/var/www/html/litp_plugins
    [[ -d $PLUGINSREPO/repodata ]] || (echo "checking $PLUGINSREPO" && mkdir -p $PLUGINSREPO/ && createrepo $PLUGINSREPO )
    # See LITPCDS-10462 - modify puppet module so that it doesn't run yum commands on every puppet run
    sed -i -e 's/onlyif  => \["yum list \$replacement"\],$/onlyif  => ["! rpm -q \$replacement \&\& yum list \$replacement"],/' \
            /opt/ericsson/nms/litp/etc/puppet/modules/package/manifests/replace_script.pp

    sed -i -e 's#\(^ *require => \)\[Class\["lvm::volume\[\([a-zA-Z0-9_-]*\)\]"\]\]#\1Lvm::Volume["\2"\]#g' /opt/ericsson/nms/litp/etc/puppet/manifests/plugins/*.pp

    filter_cached_catalog
    rm -f /opt/ericsson/nms/litp/etc/puppet/manifests/plugins/site.pp
    systemctl status puppet.service > /dev/null && systemctl stop puppet.service && sleep 5

    # LITPCDS-12173 - lock file moved from /var/lib to /var/run.  Remove both, just to be sure
    rm -f /var/lib/puppet/state/agent_catalog_run.lock /var/run/puppet/agent_catalog_run.lock

    PG_HBA_CONF="/var/opt/rh/rh-postgresql96/lib/pgsql/data/pg_hba.conf"

    if grep "hostssl*.all*.postgres" ${PG_HBA_CONF}
    then
      psql_cmd="psql -h ${hostname_orig}"
    else
      psql_cmd="psql"
    fi

    su - postgres -c "${psql_cmd} puppetdb -c 'create extension if not exists pg_trgm'"

    systemctl daemon-reload
fi

# Create litp-access group
LITP_ACCESS_GRP="litp-access"

# Create LITP socket dir
LITP_SOCKET_DIR="/var/run/litpd"
getent group $LITP_ACCESS_GRP >/dev/null || groupadd -r $LITP_ACCESS_GRP
mkdir -p $LITP_SOCKET_DIR
chgrp $LITP_ACCESS_GRP $LITP_SOCKET_DIR
chmod 0750 $LITP_SOCKET_DIR
echo "d ${LITP_SOCKET_DIR} 0750 root ${LITP_ACCESS_GRP}" > /usr/lib/tmpfiles.d/litpd.conf


# litpcrypt symlink handling
litpcrypt="/usr/bin/litpcrypt"
if [[ -h ${litpcrypt} ]]; then
    owner=$(rpm -qf ${litpcrypt})
    if [[ ${owner} == ERIClitpcli_CXP9030420* ]]; then
        unlink ${litpcrypt}
    fi
fi
ln -sf /opt/ericsson/nms/litp/lib/litp/core/litpcrypt.py ${litpcrypt}

usermod -aG puppet,litp-admin,celery,${LITP_ACCESS_GRP} celery
usermod -aG celery root
usermod -aG celery,${LITP_ACCESS_GRP} litp-admin

LITP_LOG_DIR="/var/log/litp"
declare -a LOG_FILES=("metrics.log"
                      "litpd_error.log"
                      "litpd_access.log")
for file in "${LOG_FILES[@]}"
do
   [ -f ${LITP_LOG_DIR}/${file} ] &&  chown celery:celery ${LITP_LOG_DIR}/${file}
done

for dir in ${LITP_LOG_DIR} /var/lib/cobbler/snippets
do
   chown celery:celery ${dir}
done

shopt -s nullglob
for file in /var/lib/cobbler/snippets/*.ks.partition.snippet; do
    chown celery:celery "${file}"
done

chown -R celery:puppet /opt/ericsson/nms/litp/etc/puppet/manifests
chown celery:puppet /opt/ericsson/nms/litp/etc/puppet/litp_config_version

rm -f /etc/httpd/conf.d/puppetmaster.conf

#Generate celery pid and log directories
/usr/bin/systemd-tmpfiles --create /etc/tmpfiles.d/celery.conf

POSTGRES_SERVER_CERT='/var/opt/rh/rh-postgresql96/lib/pgsql/ssl/server.crt'
MANAGE_POSTGRES_CERTS='/opt/ericsson/nms/litp/bin/manage_postgres_certs.sh'
if [ ! -f "${POSTGRES_SERVER_CERT}" ]
then
  "${MANAGE_POSTGRES_CERTS}" -g
fi

for svc in httpd puppetserver puppetserver_monitor puppet puppetdb puppetdb_monitor; do systemctl status ${svc}.service 2> /dev/null && systemctl restart ${svc}.service || systemctl start ${svc}.service; sleep 5; done
for svc in celery celerybeat; do systemctl start ${svc}.service; done

exit 0
