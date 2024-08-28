#!/bin/bash
SERVICE=/sbin/service
GREP=/bin/grep
CHKCONFIG=/sbin/chkconfig
CP=/bin/cp
OLD_DATA_DIR="/var/lib/pgsql/data"
BACKUP_DIR="/var/lib/pgsql/data-backup"
NEW_POSTGRES_VERSION="96"
NEW_DATA_DIR="/var/opt/rh/rh-postgresql${NEW_POSTGRES_VERSION}/lib/pgsql/data"
NEW_BIN_DIR="/opt/rh/rh-postgresql${NEW_POSTGRES_VERSION}/root/usr/bin/"
OLD_SERVICE_NAME="postgresql"
NEW_SERVICE_NAME="rh-postgresql${NEW_POSTGRES_VERSION}-postgresql"
UPGRADE_LOG="/var/lib/pgsql/upgrade_rh-postgresql${NEW_POSTGRES_VERSION}-postgresql.log"
LOGGER="/bin/logger"
OUT="/var/log/messages"
PSQL="/usr/bin/psql"
OLD_POSTGRES_SERVER_VERSION="8.4.20"
NEW_POSTGRES_SERVER_VERSION="9.6.5"
NR_DATABASES_EXPECTED=3
OLD_POSTGRES_SERVER_RPM="postgresql-server"
OLD_POSTGRES_CLIENT_RPM="postgresql"
OLD_POSTGRES_LIB_RPM="postgresql-libs"
SERVER_SYSPATHS_RPM="rh-postgresql96-postgresql-server-syspaths"
CLIENT_SYSPATHS_RPM="rh-postgresql96-postgresql-syspaths"
STEP="0"
MIGRATION_FAILURE_FILE="/var/lib/pgsql/postgresql_rh-postresql96_migration_status_fail"
MIGRATION_OK_FILE="/var/lib/pgsql/postgresql_rh-postresql96_migration_status_ok"
MIGRATION_NOT_REQUIRED_MSG="PostgreSQL ${NEW_POSTGRES_VERSION} migration not required"
OLD_HBA_CONF="${OLD_DATA_DIR}/pg_hba.conf"
OLD_INDENT_CONF="${OLD_DATA_DIR}/pg_ident.conf"

function log() {
    ${LOGGER} "${1}"
}

function is_postgres_migration_required() {
  if  [ -f ${MIGRATION_FAILURE_FILE} ]
  then
    log "PostgreSQL migration has previously failed. Exiting migration procedure."
    exit 1
  fi
  # This section executes when the script is called during an upgrade
  if directory_exists_and_not_empty ${OLD_DATA_DIR}
  then
    if ! check_service_is_running ${OLD_SERVICE_NAME}
    then
      exit_on_error "${OLD_SERVICE_NAME} is not running. Exiting migration procedure."
    fi

    if check_database_and_old_server_version
    then
      if [ -d ${NEW_BIN_DIR} ]
      then
        if directory_exists_and_empty ${NEW_DATA_DIR}
        then
          log "PostgreSQL ${NEW_POSTGRES_VERSION} migration required"
          return 0
        else
          exit_on_error "${NEW_DATA_DIR} is not empty. Exiting migration procedure."
        fi
      else
        exit_on_error "Directory ${NEW_BIN_DIR} does not exist. Postgres 9.6 may not be installed, exiting migration procedure."
      fi
    else
       exit_on_error "Checks on number of databases and server version 8.4.20 failed"
    fi
  # This is a fresh install of LITP on PostgreSQL-9.6
  else
    if [ ! -f ${MIGRATION_OK_FILE} ]
    then
      write_status_file ${MIGRATION_OK_FILE} "${MIGRATION_NOT_REQUIRED_MSG}"
    fi
    log "${MIGRATION_NOT_REQUIRED_MSG}"
    return 1
  fi
}

function check_database_and_old_server_version() {
  postgres_server_version=$(su - postgres -c "${PSQL} -tAc \"SHOW server_version\"")
  database_count=$(su - postgres -c "${PSQL} -tAc \"select count(*) from pg_database WHERE datname='litp' OR datname='litpcelery' OR datname='puppetdb'\"")

  if  [ "${OLD_POSTGRES_SERVER_VERSION}" = "${postgres_server_version}" ] &&
      [ "$NR_DATABASES_EXPECTED" -eq "${database_count}" ]
  then
    return 0
  else
    return 1
  fi
}

function backup_postgres_data() {
  if [ -d  ${OLD_DATA_DIR} ]
  then
    if [ ! -d ${BACKUP_DIR} ]
    then
      mkdir ${BACKUP_DIR}
    fi
    if cp -r ${OLD_DATA_DIR}/* ${BACKUP_DIR}
    then
      log "Backup complete"
    else
      log "Backup Failed"
    fi
  fi
}

function directory_exists_and_not_empty () {
  if directory_exists $1
    then
    return `test -n "$(ls -A $1)"`
  fi
  return 1
}

function directory_exists_and_empty() {
  if directory_exists $1
    then
    return `test -z "$(ls -A $1)"`
  fi
  return 1
}

function directory_exists() {
  return `test -d $1`
}

function check_service_is_running() {
  log "Checking status of $1 service"
  return `${SERVICE} $1 status | ${GREP} -iq running`
}

function delete_postgres_backup() {
    if [ -d  ${BACKUP_DIR} ]
    then
      if rm -rf ${BACKUP_DIR}
      then
        log "Successfully deleted backup"
      else
        log "Error occurred while deleting backup"
      fi
    fi
}

#supports starting or stopping a service
#$1 service name
#$2 action: start or stop
function service_action() {
  service_name=$1
  action=$2

  if [ "$action" != "start" ] && [ "$action" != "stop" ]
  then
    log "ERROR: Service action: ${action} not supported"
    return 1
  fi

  ${SERVICE} ${service_name} ${action} >> $OUT 2>&1
  sleep 2
  status=$(${SERVICE} ${service_name} status)

  if [ "${action}" = "stop" ] && [[ "${status}" = *"stopped"* ]]
  then
    log "Stopped ${service_name} service"
    return 0
  elif [ "${action}" = "start" ] && [[ "$status" = *"running"* ]]
  then
    log "Started ${service_name} service"
    return 0
  else
    log "Failed to ${action} service $service_name"
   return 1
  fi
}


function perform_migration() {
   log "Performing migration to rh_postgresql$NEW_POSTGRES_VERSION with command: scl enable rh-postgresql${NEW_POSTGRES_VERSION} -- postgresql-setup --upgrade"
   PGSETUP_INITDB_OPTIONS="--locale=C --encoding=UTF-8" scl enable rh-postgresql${NEW_POSTGRES_VERSION} -- postgresql-setup --upgrade  >> $OUT 2>&1
   if [ $? -eq 0 ] &&  ${GREP} -i "Upgrade Complete" ${UPGRADE_LOG} > /dev/null
   then
     log "pg_upgrade successfully completed"
     return 0
   else
     return 1
   fi
}

function analyse_new_cluster() {
   log "Running script to analyse new PostgreSQL $NEW_POSTGRES_VERSION cluster"
   su - postgres -c "scl enable rh-postgresql${NEW_POSTGRES_VERSION} ~/analyze_new_cluster.sh" >> $OUT 2>&1
   return $?
}

#supports enabling or disabling of a service (chkconfig on or off)
#$1 the service name to act on
#$2 "on" or "off" whether the service will be enabled (on)
#or disabled "off" at system start
function handle_service_chkconfig() {
  service_name=$1
  action=$2

  if [ "$action" != "on" ] && [ "$action" != "off" ]
  then
    log "ERROR: action $action not supported"
    return 1
  fi

  ${CHKCONFIG} $service_name $action >> $OUT 2>&1
  return $?
}

function delete_old_cluster() {
  su - postgres -c "scl enable rh-postgresql${NEW_POSTGRES_VERSION} ~/delete_old_cluster.sh"
  return $?
}

function exit_on_error() {
  error_msg="$1"

  service_action ${OLD_SERVICE_NAME} stop
  service_action ${NEW_SERVICE_NAME} stop

  log "Migration failed on step ${STEP} : ${error_msg}"
  write_status_file ${MIGRATION_FAILURE_FILE} "Migration failed on step ${STEP} : ${error_msg}"
  exit 1
}

function exit_on_success() {
  write_status_file ${MIGRATION_OK_FILE} "Migration Successful"
  delete_postgres_backup
  exit 0
}

function write_status_file() {
  cat << EOF > $1
$2
EOF
}

function copy_old_conf_files() {
  err_msg=$1
  for file in ${OLD_INDENT_CONF} ${OLD_HBA_CONF}
  do
    if ! \cp $file ${NEW_DATA_DIR}
    then
      exit_on_error "${err_msg} Could not copy ${file} to ${NEW_DATA_DIR}"
    fi
  done
  return 0
}

function uninstall_rpm() {
  rpm=$1
  nodeps=$2
  rpm_command=""

  rpm -q ${rpm} > /dev/null 2>&1
  res=$?
  if [ ${res} -eq 0 ]
  then
    if [ "${nodeps}" = "nodeps" ]
    then
      rpm_command="rpm -e --nodeps ${rpm}"
    else
      rpm_command="rpm -e ${rpm}"
    fi
  else
    log "Error: Couldn't find rpm: ${rpm} to uninstall"
    return ${res}
  fi

  log "Uninstalling: ${rpm} with command: ${rpm_command}"
  ${rpm_command} >> $OUT 2>&1
  res=$?
  if [ ${res} -ne 0 ]
  then
    log "Error: Failed to uninstall rpm ${rpm}"
  fi

  return $res
}

function perform_migration_sequence() {

  backup_postgres_data

  error_msg="PostgreSQL migration from ${OLD_POSTGRES_SERVER_VERSION} to ${NEW_POSTGRES_SERVER_VERSION} failed: "

  log "Starting PostgreSQL migration from PostgreSQL version ${OLD_POSTGRES_SERVER_VERSION} to ${NEW_POSTGRES_SERVER_VERSION}"

  #Step 1: Stop the old PostgreSQL service
  log "Stopping ${OLD_SERVICE_NAME} service"
  STEP="1"
  service_action ${OLD_SERVICE_NAME} stop ||
  exit_on_error "${error_msg} Could not stop ${OLD_SERVICE_NAME} service"

  #Step 2: Perform migration
  STEP="2"
  perform_migration || exit_on_error "${error_msg} pg_upgrade failed"

  #Step 3: Copy configuration files from the old data directory to the new one
  STEP="3"
  copy_old_conf_files "${error_msg}" && log "Successfully copied ${OLD_INDENT_CONF} and ${OLD_HBA_CONF} to ${NEW_DATA_DIR}"

  #Step 4: Start the new PostgreSQL 9.6 service
  STEP="4"
  logger "Starting new ${NEW_SERVICE_NAME} service"
  service_action ${NEW_SERVICE_NAME} start ||
  exit_on_error "${error_msg} Failed to start ${NEW_SERVICE_NAME}"

  #Step 5: Analyse new cluster
  STEP="5"
  logger "Running analyze_new_cluster.sh"
  analyse_new_cluster ||
  exit_on_error "${error_msg} analyze_new_cluster failed"

  #Step 6: Disable the old service
  STEP="6"
  logger "Disabling the old ${OLD_SERVICE_NAME} service"
  handle_service_chkconfig ${OLD_SERVICE_NAME} "off" ||
  exit_on_error "${error_msg} Failed to disable the old $OLD_SERVICE_NAME service"

  #Step 7: enable the new service
  STEP="7"
  logger "Enabling the new ${NEW_SERVICE_NAME} service"
  handle_service_chkconfig ${NEW_SERVICE_NAME} "on" ||
  exit_on_error "${error_msg} Failed to enable the new ${NEW_SERVICE_NAME} service"

  #Step 8: Unistall Postgres 8.4 rpms
  STEP="8"
  uninstall_rpm ${OLD_POSTGRES_SERVER_RPM} ||
  exit_on_error "${error_msg} Could not uninstall rpm ${OLD_POSTGRES_SERVER_RPM}"

  uninstall_rpm ${OLD_POSTGRES_CLIENT_RPM} "nodeps" ||
  exit_on_error "${error_msg} Could not uninstall rpm ${OLD_POSTGRES_CLIENT_RPM}"

  uninstall_rpm ${OLD_POSTGRES_LIB_RPM} ||
  exit_on_error "${error_msg} Could not uninstall rpm ${OLD_POSTGRES_LIB_RPM}"

  #Step 9: Install the syspath packages
  STEP="9"
  yum install -y ${SERVER_SYSPATHS_RPM} ||
  exit_on_error "${error_msg} Could not install rpm ${SERVER_SYSPATHS_RPM}"

  yum install -y ${CLIENT_SYSPATHS_RPM} ||
  exit_on_error "${error_msg} Could not install rpm ${CLIENT_SYSPATHS_RPM}"

  #Step 10: Delete the old data area
  STEP="10"
  logger "Deleting the old data area, running delete_old_cluster.sh"
  delete_old_cluster ||
  exit_on_error "${error_msg} delete_old_cluster.sh failed"

  exit_on_success
}

#main
if is_postgres_migration_required
then
   perform_migration_sequence
fi

