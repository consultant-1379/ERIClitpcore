#!/bin/bash
#Script to generate LMS PostgreSQL client and server certs
#Uses the method described here: https://luppeng.wordpress.com/2021/08/07/create-and-install-ssl-certificates-for-postgresql-database-running-locally/

readonly POSTGRES_SSL_DIR='/var/opt/rh/rh-postgresql96/lib/pgsql/ssl'
readonly CA_CERT="${POSTGRES_SSL_DIR}/ca.crt"
readonly CA_KEY="${POSTGRES_SSL_DIR}/ca.key"
readonly CA_SRL="${POSTGRES_SSL_DIR}/ca.srl"
readonly SERVER_CSR="${POSTGRES_SSL_DIR}/server.csr"
readonly SERVER_KEY="${POSTGRES_SSL_DIR}/server.key"
readonly SERVER_CERT="${POSTGRES_SSL_DIR}/server.crt"
readonly OPENSSL='/usr/bin/openssl'
readonly ECHO='/usr/bin/echo'
readonly ROOT_CLIENT_DIR='/root/.postgresql'
readonly CELERY_CLIENT_DIR='/home/celery/.postgresql'
readonly POSTGRES_CLIENT_DIR='/var/lib/pgsql/.postgresql'
readonly RM='/usr/bin/rm'
readonly CHOWN='/usr/bin/chown'
readonly CHMOD='/usr/bin/chmod'
readonly SYSTEMCTL='/usr/bin/systemctl'
readonly MCO='/usr/bin/mco'
readonly SLEEP='/usr/bin/sleep'
readonly CLIENT_KEY='postgresql.key'
readonly CLIENT_CSR='postgresql.csr'
readonly CLIENT_CERT='postgresql.crt'
readonly CLIENT_ROOT_CERT='root.crt'
readonly INITIAL_CERT_VALIDITY_PERIOD=$((365*50))
readonly POSTGRES_SERVICE='postgresql.service'
readonly FILE_PERMISSIONS=0600
readonly DIRECTORY_PERMISSIONS=0700
readonly LOGGER='/bin/logger'
readonly BASENAME='/usr/bin/basename'
readonly SCRIPT_NAME=$("${BASENAME}" "$0")
readonly ID='/usr/bin/id'
export HOME=/root
echo_output=1
verbose=0
hostname=$(hostname)
cert_validity_period=${INITIAL_CERT_VALIDITY_PERIOD}
generate_certs=0
regenerate_certs=0
check_cert_health=0
show_cert_expiry=0
help=0
cert_validity=0
cert_validity_arg=""
declare -a script_args=()
declare -a actions=()

declare -ra SERVICES=("puppet.service" "litpd.service" "celery.service"
                      "celerybeat.service")

declare -ra SERVER_FILES=("${CA_CERT}" "${CA_KEY}" "${CA_SRL}"
                          "${SERVER_KEY}" "${SERVER_CSR}" "${SERVER_CERT}")

declare -ra CLIENT_FILES=("${CLIENT_KEY}" "${CLIENT_CSR}" "${CLIENT_CERT}"
                          "${CLIENT_ROOT_CERT}")

declare -rA CLIENT_CERT_DIRS=(["litp"]="${ROOT_CLIENT_DIR} ${CELERY_CLIENT_DIR}"
                              ["postgres"]="${POSTGRES_CLIENT_DIR}")

declare -rA DB_USER_MAPPING=(["litp"]="root celery"
                             ["postgres"]="postgres")

declare -ra GENERATE_CERT_STEPS=("check_script_run_as_root" "check_system_users_exist"
                                 "check_certs_not_generated" "gen_server_certs"
                                 "gen_client_certs")

declare -rA GENERATE_CERT_STEP_MSGS=(["check_script_run_as_root"]="Step 1: Check script is run as root"
                                     ["check_system_users_exist"]="Step 2: Check system users exist"
                                     ["check_certs_not_generated"]="Step 3: Check certs not previously generated"
                                     ["gen_server_certs"]="Step 4: Generate PostgreSQL server certs"
                                     ["gen_client_certs"]="Step 5: Generate PostgreSQL client certs")

declare -ra REGENERATE_CERT_STEPS=("check_script_run_as_root" "check_system_users_exist"
                                   "disable_puppet" "stop_services" "remove_all_certs"
                                   "gen_server_certs" "gen_client_certs"
                                   "start_services" "enable_puppet")

declare -rA REGENERATE_CERT_STEP_MSGS=(["check_script_run_as_root"]="Step 1: Check script is run as root"
                                       ["check_system_users_exist"]="Step 2: Check system users exist"
                                       ["disable_puppet"]="Step 3: Disable puppet"
                                       ["stop_services"]="Step 4: Stop services"
                                       ["remove_all_certs"]="Step 5: Remove all PostgreSQL client and server certs"
                                       ["gen_server_certs"]="Step 6: Generate PostgreSQL server certs"
                                       ["gen_client_certs"]="Step 7: Generate PostgreSQL client certs"
                                       ["start_services"]="Step 8: Start services"
                                       ["enable_puppet"]="Step 9: Enable puppet")

declare -ra CHECK_CERT_HEALTH=("check_server_cert_health" "check_client_cert_health")
declare -rA CHECK_CERT_HEALTH_MSGS=(["check_server_cert_health"]="Step 1: Server cert checks"
                                    ["check_client_cert_health"]="Step 2: Client cert checks")


function gen_priv_key {
  local key=${1}
  local requester_name=${2}

  log "Generating ${requester_name} private key"
  run_command "${OPENSSL} ecparam -name prime256v1 -genkey -noout -out ${key}"
}


function gen_ca_key_and_cert {
  gen_priv_key "${CA_KEY}" "CA"

  log "Generating CA cert"
  run_command "${OPENSSL} req -new -x509 -sha256 -key ${CA_KEY} -out ${CA_CERT} -days ${cert_validity_period} -subj /CN=ROOTCA"
}

function gen_private_key_and_csr {
  local key=${1}
  local csr=${2}
  local cn=${3}
  local requester_name=${4}

  gen_priv_key "${key}" "${requester_name}"

  log "Generating ${requester_name} CSR"
  run_command "${OPENSSL} req -new -sha256 -key ${key} -out ${csr} -subj /CN=${cn}"
}

function gen_cert {
  local csr=${1}
  local cert=${2}
  local requester_name=${3}

  #use the self-managed CA private key and cert to sign the client’s CSR and generate the cert
  log "Generating ${requester_name} cert"
  run_command "${OPENSSL} x509 -req -in ${csr} -CA ${CA_CERT} -CAkey ${CA_KEY} -CAcreateserial -out ${cert} -days ${cert_validity_period} -sha256"
}

function gen_server_certs {
  #create server cert dir
  create_dir "${POSTGRES_SSL_DIR}"

  #change ownership and permissions on server cert dir
  change_owner "postgres" "postgres" "${POSTGRES_SSL_DIR}"
  change_permissions "${DIRECTORY_PERMISSIONS}" "${POSTGRES_SSL_DIR}"

  #Create the private key and cert belonging to self-managed CA
  gen_ca_key_and_cert

  #Generate a private key and a Cert Signing Request (CSR) for the PostgreSQL server
  gen_private_key_and_csr "${SERVER_KEY}" "${SERVER_CSR}" "${hostname}" "PostgreSQL server"

  #Use the self-managed CA private key and cert to sign the CSR and generate the server cert
  gen_cert "${SERVER_CSR}" "${SERVER_CERT}" "PostgreSQL server"

  #Change the owner and permissions on server cert and server key and csr
  for file in "${SERVER_FILES[@]}"
  do
    change_owner "postgres" "postgres" "${file}"
    change_permissions "${FILE_PERMISSIONS}" "${file}"
  done
}

function gen_client_certs {
  for db_user in "${!CLIENT_CERT_DIRS[@]}"
  do
    read -r -a client_dirs <<< "${CLIENT_CERT_DIRS[${db_user}]}"
    #where multiple system users log in as the same db user,
    #certs will be created in the first client dir, and then copied to subsequent dirs
    create_dir "${client_dirs[0]}"

    #Generate a private key and a Cert Signing Request (CSR) for the db client
    gen_private_key_and_csr "${client_dirs[0]}/${CLIENT_KEY}" "${client_dirs[0]}/${CLIENT_CSR}" "${db_user}" "${db_user} db user"

    #Use the self-managed CA private key and cert to sign the CSR and generate the client cert
    gen_cert "${client_dirs[0]}/${CLIENT_CSR}" "${client_dirs[0]}/${CLIENT_CERT}" "${db_user} db user"

    copy_certs_for_additional_clients "${client_dirs[@]}"

    copy_root_cert "${client_dirs[@]}"

    change_client_permissions "${db_user}"
  done
}

function copy_root_cert {
  declare -a client_dirs=($@)

  log "Copying root cert to client directories"
  for dir in "${client_dirs[@]}"
  do
     run_command "cp -f ${CA_CERT} ${dir}/root.crt"
  done
}


function create_dir {
  local dir=${1}

  [ ! -d "${dir}" ] && log "Creating directory: ${dir}" && run_command "mkdir -p ${dir}"
}

#Copies certs from the first client directory
#into subsequent directories
function copy_certs_for_additional_clients {
  declare -a client_dirs=($@)

  for dir in "${client_dirs[@]:1}"
  do
    create_dir "${dir}"
    log "Copying client certs"
    run_command "cp -f ${client_dirs[0]}/*  ${dir}/"
  done
}

function change_owner {
  local user=${1}
  local group=${2}
  local file=${3}

  log "Changing ownership of: ${file}"
  run_command "${CHOWN} ${user}:${group} ${file}"
}

function change_permissions {
  local permissions=${1}
  local file=${2}

  log "Changing permissions on: ${file}"
  run_command "${CHMOD} ${permissions} ${file}"
}


function change_client_permissions {
  local db_user=${1}

  read -r -a client_dirs <<< "${CLIENT_CERT_DIRS[${db_user}]}"
  read -r -a system_users <<< "${DB_USER_MAPPING[${db_user}]}"

  index=0
  element_count=${#client_dirs[@]}
  while [ "${index}" -lt "${element_count}" ]
  do
     change_permissions "${DIRECTORY_PERMISSIONS}" "${client_dirs[${index}]}"
     change_owner "${system_users[${index}]}" "${system_users[${index}]}" "${client_dirs[${index}]}"

     for file in "${CLIENT_FILES[@]}"
     do
       change_permissions "${FILE_PERMISSIONS}" "${client_dirs[${index}]}/${file}"
       change_owner "${system_users[${index}]}" "${system_users[${index}]}" "${client_dirs[${index}]}/${file}"
     done
     ((index++))
  done
}


function remove_file {
  local file_to_remove=${1}

  [ -f "${file_to_remove}" ] && log "Removing file ${file_to_remove}" && run_command "${RM} -f ${file_to_remove}"
}


function remove_files {
  local files_to_remove=("$@")

  for file in "${files_to_remove[@]}"
  do
    remove_file "${file}"
  done
}

function remove_server_certs {
  remove_files "${SERVER_FILES[@]}"
}

function remove_client_certs {
  for db_user in "${!CLIENT_CERT_DIRS[@]}"
  do
    for dir in ${CLIENT_CERT_DIRS[${db_user}]}
    do
       for file in "${CLIENT_FILES[@]}"
       do
         remove_file "${dir}/${file}"
       done
    done
  done
}

#Function to start or stop
#a service
function service_action {
  local action=${1}
  shift
  local services=("$@")

  for svc in "${services[@]}"
  do
    [ 'stop' = "${action}" ] && log "Stopping service ${svc}"
    [ 'start' = "${action}" ] && log "Starting service ${svc}"
    run_command "${SYSTEMCTL} ${action} ${svc}"
    check_services_status "${action}" "${svc}"
  done
}

function remove_all_certs {
  remove_server_certs
  remove_client_certs
}

function generate_certs {
  log "Generating PostgreSQL client and server certs"
  for step in "${GENERATE_CERT_STEPS[@]}"
  do
    run_step "${step}" "${GENERATE_CERT_STEP_MSGS[${step}]}"
  done
  log "Successfully generated PostgreSQL client and server certs"
}

function stop_services {
  service_action stop "${SERVICES[@]}" "${POSTGRES_SERVICE}"
}

function start_services {
  service_action start "${POSTGRES_SERVICE}" "${SERVICES[@]}"
}

function check_services_status {
  local service_action=${1}
  local service=${2}
  local cmd="${SYSTEMCTL} is-active ${service}"

  for iter in {1..30}
  do
    ${cmd} 2>&1 | ${LOGGER}
    res="${PIPESTATUS[0]}"
    log "Executed cmd: ${cmd}, result: ${res}"

    if [[ 'stop' = "${service_action}" && 0 -ne "${res}" ]]
    then
      log "Service ${service} stopped."
      break
    elif [[ 'start' = "${service_action}" && 0 -eq "${res}" ]]
    then
      log "Service ${service} started."
      break
    fi

    if [ ${iter} -ge 30 ]
    then
        log "ERROR: Service ${service} failed to ${service_action}" && exit 1
    fi

    log "Wait for Service ${service} to ${service_action}"
    ${SLEEP} 2
  done
}

function disable_puppet {
  log "Disabling puppet"
  run_puppet_command "${MCO} puppet disable -I ${hostname}"
}

function enable_puppet {
  log "Enabling puppet"
  run_puppet_command "${MCO} puppet enable -I ${hostname}"
}

#check if system users exist
function check_system_users_exist {
  for system_users in "${DB_USER_MAPPING[@]}"
  do
    for system_user in ${system_users}
    do
      log "Checking if system user ${system_user} exists"
      run_command "${ID} ${system_user}"
    done
  done
}

function check_script_run_as_root {
  run_command "[ 0 -eq ${EUID} ]" "ERROR: Script must be run as root user."
}

function regenerate_certs {
   log "Re-generating PostgreSQL client and server certs"
   for step in "${REGENERATE_CERT_STEPS[@]}"
   do
     run_step "${step}" "${REGENERATE_CERT_STEP_MSGS[${step}]}"
   done
   log "Successfully re-generated PostgreSQL client and server certs"
}

function check_certs_not_generated {
  check_server_certs_not_generated
  check_client_certs_not_generated
}

function check_server_certs_not_generated {
  for file in "${SERVER_FILES[@]}"
  do
    check_file_absent "${file}" "Server"
  done
}

function check_client_certs_not_generated {
  for db_user in "${!CLIENT_CERT_DIRS[@]}"
  do
    for dir in ${CLIENT_CERT_DIRS[${db_user}]}
    do
       for file in "${CLIENT_FILES[@]}"
       do
         check_file_absent "${dir}/${file}" "Client"
       done
    done
  done
}

function check_file_absent {
  local file=${1}
  local requester_name=${2}
  err_msg="ERROR: ${requester_name} certs already exist. File: ${file} is present. Use the -r option to regenerate certs"

  log "Checking ${file} not present"
  [ -f "${file}" ] && log "${err_msg}" && "${ECHO}" "${err_msg}" && exit 1
}


function check_file_exists {
  local file=${1}

  run_command "[ -f ${file} -o -d ${file} ]" "ERROR: ${file} doesn't exist"
  [ -f "${file}" ] && run_command "[ -s ${file} ]" "ERROR: ${file} is empty"
}

function check_permissions {
  local file=${1}
  expected_mode=${2}

  mode=$(stat -c '%a' "${file}")
  run_command "[ ${expected_mode} -eq ${mode} ]" "ERROR: Permissions ${mode} on: ${file} not as expected: ${expected_mode}"
}

function check_owner {
  local file=${1}
  local expected_user=${2}
  local expected_group=${3}
  local user
  local group

  user=$(stat -c '%U' "${file}")
  group=$(stat -c '%G' "${file}")

  run_command "[ ${expected_user} = ${user} ]" "ERROR: Owner user name: ${user} on ${file} not as expected: ${expected_user}"
  run_command "[ ${expected_group} = ${group} ]" "ERROR: Owner group name: ${group} on ${file} not as expected: ${expected_group}"
}

function check_server_cert_health {
  for file in "${POSTGRES_SSL_DIR}" "${SERVER_FILES[@]}"
  do
    check_file_exists "${file}"
    [ -d "${file}" ] &&  check_permissions "${file}" "${DIRECTORY_PERMISSIONS}"
    [ -f "${file}" ] &&  check_permissions "${file}" "${FILE_PERMISSIONS}"
    check_owner "${file}" "postgres" "postgres"
  done
}

function check_client_cert_health {
  for db_user in "${!CLIENT_CERT_DIRS[@]}"
  do
    read -r -a client_dirs <<< "${CLIENT_CERT_DIRS[${db_user}]}"
    read -r -a system_users <<< "${DB_USER_MAPPING[${db_user}]}"

    local index=0
    local element_count=${#client_dirs[@]}
    while [ "${index}" -lt "${element_count}" ]
    do
       check_file_exists "${client_dirs[${index}]}"
       check_permissions "${client_dirs[${index}]}" "${DIRECTORY_PERMISSIONS}"
       check_owner "${client_dirs[${index}]}" "${system_users[${index}]}" "${system_users[${index}]}"

       for file in "${CLIENT_FILES[@]}"
       do
         check_file_exists "${client_dirs[${index}]}/${file}"
         check_permissions "${client_dirs[${index}]}/${file}" "${FILE_PERMISSIONS}"
         check_owner "${client_dirs[${index}]}/${file}" "${system_users[${index}]}" "${system_users[${index}]}"
       done
      ((index++))
    done
  done
}

function check_cert_health {
  log "Running cert health check"
  for step in "${CHECK_CERT_HEALTH[@]}"
  do
    run_step "${step}" "${CHECK_CERT_HEALTH_MSGS[${step}]}"
  done
  log "Sucessfully completed cert health check"
}

function show_all_cert_expiry {
  log "********Show cert expiry********"
  show_server_cert_expiry
  show_client_cert_expiry
  log "********Successfully showed cert expiry********"
}

function show_server_cert_expiry {
   show_cert_expiry "${SERVER_CERT}" "PostgreSQL server"
   show_cert_expiry "${CA_CERT}" "PostgreSQL server CA"
}

function show_client_cert_expiry {
  for db_user in "${!CLIENT_CERT_DIRS[@]}"
  do
    for dir in ${CLIENT_CERT_DIRS[${db_user}]}
    do
        show_cert_expiry "${dir}/${CLIENT_CERT}" "${db_user} db user"
        show_cert_expiry "${dir}/${CLIENT_ROOT_CERT}" "${db_user} db user root"
    done
  done
}

function show_cert_expiry {
  local cert=${1}
  local requester_name=${2}
  local expiry_date

  expiry_date=$("${OPENSSL}" x509 -enddate -noout -in "${cert}" | awk -F '=' '{print $NF}')

  log "${requester_name} cert ${cert} expires on ${expiry_date}"
}

function run_command {
  local cmd=${1}
  local msg=${2:-"ERROR: Command ${cmd} failed: ${res}"}

  ${cmd} 2>&1 | ${LOGGER}
  local res="${PIPESTATUS[0]}"

  [ 0 -ne "${res}" ] && log "${msg}" && exit 1

  verbose_on && log "Executed cmd: ${cmd}, result: ${res}"
}

# To tolerate puppet enabled/disabled error and allow re-running the script
function run_puppet_command {
  local cmd=${1}

  local puppet_enable_substr="Could not enable Puppet: Already enabled"
  local puppet_disable_substr="Could not disable Puppet: Already disabled"
  local res_puppet

  res_puppet=$(${cmd})
  local res="${PIPESTATUS[0]}"
  if [[ 2 -eq "${res}" && "$res_puppet" == *"$puppet_enable_substr"* ]]; then
    log "Puppet already enabled"
  elif [[ 2 -eq "${res}" && "$res_puppet" == *"$puppet_disable_substr"*  ]]; then
    log "Puppet already disabled"
  elif [ 0 -ne "${res}" ]; then
    log "ERROR: Command ${cmd} failed: ${res}"
    exit 1
  else
    log "Executed cmd: ${cmd}, result: ${res}"
  fi
}


function get_days_in_time_period {

  local time_period=$1
  local time_unit=$2

py_get_days_in_time_period=$(cat <<EOF
from datetime import date
from dateutil.relativedelta import relativedelta
import sys
current_date=date.today()
try:
  future_date = current_date + relativedelta(${time_unit}=+${time_period})
except Exception as e:
  print 'Error: {0}. Ensure time period entered does not exceed the date 31st December 9999'.format(str(e))
  sys.exit(1)
print((future_date - current_date).days)
sys.exit(0)
EOF
)

  days_in_time_period=$(python -c "${py_get_days_in_time_period}")
  result=$?
  "${ECHO}" "${days_in_time_period}"
  return ${result}
}

function log {
  local msg=${1}

  should_echo_output && "${ECHO}" "${SCRIPT_NAME}: ${msg}"
  "${LOGGER}" "${SCRIPT_NAME}: ${msg}"
}

function should_echo_output {
  [ 0 -eq "${echo_output}" ] && return 0
  return 1
}

function verbose_on {
  [ 0 -eq "${verbose}" ] && return 0
  return 1
}

function exit_with_usage_msg {
   ${SLEEP} 1
    usage_msg
    exit 1
}

function run_step {
  local step_function=${1}
  local step_msg=${2}

  log "********Running ${step_msg}*********"
  "${step_function}"
  log "********${step_msg} completed successfully********"
}

function check_user_input {
  if [ "${OPTIND}" -eq 1 ];
  then
    "${ECHO}" "ERROR: Valid option not supplied"
    exit_with_usage_msg
  fi

  if [ -n "${cert_validity_arg}" ]
  then
    if [ $((regenerate_certs + generate_certs)) -ne 1 ]
    then
      "${ECHO}" "ERROR: Use the -t option with the -r or -g options"
      exit_with_usage_msg
    fi

    if [ "${cert_validity}" -gt 1 ]
    then
      "${ECHO}" "ERROR: -t option should be specified once"
      exit_with_usage_msg
    fi

    if ! [[ "${cert_validity_arg}" =~ ^[1-9][0-9]*[dDmMyY]$ ]]
    then
      "${ECHO}" "ERROR: Cert validity period must be a natural non-zero number, followed by a time unit, d, D, m, M, y or Y"
      exit_with_usage_msg
    fi
  fi

  if [ 0 -ne ${#script_args[@]} ]
  then
    "${ECHO}" "ERROR: Unexpected argument(s) found: ${script_args[*]}"
    exit_with_usage_msg
  fi

  if [ $((regenerate_certs + generate_certs + show_cert_expiry + check_cert_health + help)) -ne 1 ]
  then
    "${ECHO}" "ERROR: Use one of the -g, -r, -e, -c, -h options at a time"
    exit_with_usage_msg
  fi
}


function calculate_cert_validity_period {
  if [ -n "${cert_validity_arg}" ]
  then
    time_period=${cert_validity_arg:0:((${#cert_validity_arg}-1))}
    time_unit=${cert_validity_arg:((${#cert_validity_arg}-1)):1}

    case "${time_unit,,}" in
      d) cert_validity_period=$(get_days_in_time_period "${time_period}" "days")
         ;;
      m) cert_validity_period=$(get_days_in_time_period "${time_period}" "months")
         ;;
      y) cert_validity_period=$(get_days_in_time_period "${time_period}" "years")
         ;;
      *) "${ECHO}" "ERROR: Invalid time unit found: ${time_unit,,}"
         exit_with_usage_msg
    esac
  else
    cert_validity_period=$(get_days_in_time_period "50" "years" )
  fi
  result=$?
  [ 0 -ne "${result}" ] && "${ECHO}" "${cert_validity_period}" && exit_with_usage_msg
}

function run_actions {
  for action in "${actions[@]}"
  do
    "${action}"
  done
}

function usage_msg {
   ${ECHO} "
   Usage: ${SCRIPT_NAME}  { -hgrcet }

   Options:
      -h  : Display usage information.
      -g  : Generate LMS PostgreSQL db client and server certs
      -r  : Remove existing certs, and re-generate PostgreSQL LMS db client and server certs
      -c  : Run cert health check
      -e  : Print cert expiry
      -t  : Optional time period after which the certs will expire, used with the -r or -g option.
            Supply a natural number followed by one time unit: d for days, m for months, y for years.
            For example, to create a cert valid for 50 years, use -t 50y.
            The time period supplied cannot exceed the date 31st December 9999.
            If this option isn't supplied, default cert expiry is after 50 years.

   Examples:
      Display usage information: ${SCRIPT_NAME} -h
      Run cert health check: ${SCRIPT_NAME} -c
      Show cert expiry: ${SCRIPT_NAME} -e
      Regenerate PostgreSQL LMS db client and server certs: ${SCRIPT_NAME} -r
      Regenerate PostgreSQL LMS db client and server certs with 1 year validity period:
      ${SCRIPT_NAME} -r -t 1y
   "
}

while [ ${OPTIND} -le "$#" ]
do
  if getopts "hgrcet:" option
  then
    case ${option} in
      h) ((help++))
         actions+=("usage_msg")
         ;;
      g) ((generate_certs++))
         actions+=("generate_certs")
         ;;
      r) echo_output=0
         ((regenerate_certs++))
         actions+=("regenerate_certs")
         ;;
      c) verbose=1
         echo_output=0
         ((check_cert_health++))
         actions+=("check_cert_health")
         ;;
      e) verbose=1
         echo_output=0
         ((show_cert_expiry++))
         actions+=("show_all_cert_expiry")
         ;;
      t) cert_validity_arg="${OPTARG}"
         ((cert_validity++))
         ;;
      *) "${ECHO}" "ERROR: Invalid option or argument supplied"
          exit_with_usage_msg
    esac
  else
    script_args+=("${!OPTIND}")
    ((OPTIND++))
  fi
done

check_user_input
calculate_cert_validity_period
run_actions