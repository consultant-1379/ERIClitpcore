#!/bin/bash
# litpd    Ericsson LITP service daemon
###################################

SERVICE=litpd
LITP_HOME=/opt/ericsson/nms/litp/
PYTHONPATH=$LITP_HOME:$LITP_HOME/lib:$LITP_HOME/3pps/lib/python
PROCESS=$LITP_HOME/bin/litp_service.py
CONFIG_ARGS=" "
LITP_DIR=/var/lib/litp
CORE_DIR=$LITP_DIR/core
PLUGINS_DIR=$LITP_DIR/plugins
CONTRIB_DIR=$LITP_DIR/contrib
LITP_DIRS="$CORE_DIR $PLUGINS_DIR $CONTRIB_DIR"
PIDFILE=/var/run/litp_service.py.pid
STARTUPLOCK=/var/run/litp_startup_lock
CERT_HEALTHCHECKER=$LITP_HOME/bin/manage_postgres_certs.sh

LITP_CONFIG_FILE=/etc/litpd.conf

LITP_DB_AUTO_UPGRADE=YES
LITP_DB_AUTO_CREATE_DEFAULT_MODEL=YES
LITP_DB_CHECK_DB=YES
LITP_DB_CHECK_MODEL=YES
LITP_DB_CERT_CHECK=YES

LITP_E_MULTIPLE_CURRENTS=$(python -m litp.data.constants E_MULTIPLE_CURRENTS) || exit $?
LITP_E_MULTIPLE_HEADS=$(python -m litp.data.constants E_MULTIPLE_HEADS) || exit $?
LITP_E_NOTHING_APPLIED=$(python -m litp.data.constants E_NOTHING_APPLIED) || exit $?
LITP_E_UPGRADE_REQUIRED=$(python -m litp.data.constants E_UPGRADE_REQUIRED) || exit $?
LITP_E_NO_MODEL=$(python -m litp.data.constants E_NO_MODEL) || exit $?
LITP_E_MODEL_EXISTS=$(python -m litp.data.constants E_MODEL_EXISTS) || exit $?

LITP_E_NO_LEGACY_STORE=$(python -m litp.data.constants E_NO_LEGACY_STORE) || exit $?
LITP_E_LEGACY_STORE_EXISTS=$(python -m litp.data.constants E_LEGACY_STORE_EXISTS) || exit $?



. /etc/rc.d/init.d/functions

[ -r /etc/sysconfig/litpd ] && . /etc/sysconfig/litpd
[ -x $PROCESS ] || exit 5


get_litp_config_value(){
key=$1
section="global"
python - <<EOF
try:
    from ConfigParser import SafeConfigParser
    config = SafeConfigParser()
    config.read("$LITP_CONFIG_FILE")
    print config.get("${section}", "${key}").strip('\'"')
except:
    print ''
EOF
}


__check_user() {
    if (( $EUID != 0 )); then
        echo "Permission denied."
        exit 4
    fi
}


__wait_for_http_tcp_server() {
    timeout=10
    port=$(get_litp_config_value server.socket_port)
    [ -z "${port}" ] && return

    until curl -s -k https://localhost:"${port}"/ \
        | grep "Powered by a webserver" > /dev/null 2>&1
    do
        (( timeout == 0 )) && break
        let timeout--
        sleep 1
    done

    #Gets the return codes from commands from the curl pipeline
    # and copies them to a new array
    RC=( "${PIPESTATUS[@]}" )

    #Checks if the grep return codes exists and is equal to 0
    if [[ ! -z ${RC[1]} ]] && [[ ${RC[1]} -eq 0  ]]; then
       return 0
    fi

    if [[ ${timeout} -eq 0 ]]; then
        echo_failure
        echo -e "HTTP TCP server did not come up after 10 seconds."
        return 1
    fi
}


__wait_for_http_unix_socket_server() {
    timeout=10
    socket_file=$(get_litp_config_value litp_socket_file)
    [ -z "${socket_file}" ] && return

    until echo -e "GET / HTTP/1.0\r\n\r\n" | nc -U "${socket_file}" 2> /dev/null \
        | grep "Powered by a webserver" > /dev/null 2>&1
    do
        (( timeout == 0 )) && break
        let timeout--
        sleep 1

    done

    #Gets the return codes from commands from the HTTP GET pipeline
    # and copies them to a new array
    RC=( "${PIPESTATUS[@]}" )

    #Checks if the grep return codes exists and is equal to 0
    if [[ ! -z ${RC[2]} ]] && [[ ${RC[2]} -eq 0  ]]; then
       return 0
    fi

    if [ ${timeout} -eq 0 ]; then
        echo_failure
        echo -e "HTTP unix socket server did not come up after 10 seconds."
        return 1
    fi
}


__acquire_startup_lock() {
    # Maybe we should check to see whether there exists a LITP process
    # *BEFORE* we even try to acquire a startup lock
    running_pid=$(pgrep -xf "python ${PROCESS} --daemonize")
    if [[ -n ${running_pid} ]]; then
        return 1
    fi

    set -o noclobber
    { echo $$ > ${STARTUPLOCK}; } &> /dev/null
    lock_acquired=$?
    if (( lock_acquired == 0 )); then
        # No startup lockfile was found, it's ours alone
        trap '__release_startup_lock; exit 1' 2 3 15
        return ${lock_acquired}
    fi

    # There already exists a startup lock file... but is it valid?
    __check_startup_lock_valid && return ${lock_acquired}

    # The startup lock file is invalid because the init script
    # bash process that created it has terminated
    __release_startup_lock;
    __acquire_startup_lock;
    return ${?}
}

__check_startup_lock_valid() {
    read startup_lock_owner < ${STARTUPLOCK}
    if [[ -n ${startup_lock_owner} ]] && [[ -d /proc/${startup_lock_owner} ]]; then
        # Is this a valid init script process?
        executable=$(readlink /proc/${startup_lock_owner}/exe)
        if [[ ${executable} == */bin/bash ]]; then
            for argv_token in $(tr '\000' '\n' < /proc/${startup_lock_owner}/cmdline); do
                # The existing startup lock file is valid
                [[ ${argv_token} == *litpd ]] && return 0
            done
        fi
    fi
    return 1
}

__release_startup_lock() {
    [[ -w ${STARTUPLOCK} ]] && rm -f ${STARTUPLOCK}
}

__recreate_pid_file() {
    running_pid=$(pgrep -xf "python ${PROCESS} --daemonize")

    # We have a running litp process and no pid file
    if [[ ! -s ${PIDFILE} ]] && [[ -n ${running_pid} ]]; then
        # If we have a valid startup lock file, then we mustn't touch the PID
        # file
        if [[ -s ${STARTUPLOCK} ]]; then
            __check_startup_lock_valid && return
        else
            for litp_pid in ${running_pid}; do
                read -a litp_process_stats < /proc/${litp_pid}/stat
                # Check the process's PPID
                if (( ${litp_process_stats[3]} != 1 )); then
                    echo $"Another litpd service is currently starting. Exiting"
                    exit 0
                fi
            done
        fi

        echo "The litpd service is running but no pid file exists - recreating pid file"
        echo ${running_pid} > ${PIDFILE}
        chmod 0644 $PIDFILE
    fi
}

start() {
    echo -n $"Starting litp daemon: "
    # The LITP process will create its own PID file through CherryPy's
    # 'Daemonizer' plugin.
    # We need a separate mutual exclusion device to cover the case where a LITP
    # service has been started after a previous service that has not yet
    # created its PID file, particularly now that we have to handle database
    # upgrade actions as part of the startup, as below.
    __acquire_startup_lock
    if (( $? != 0 )); then
        echo_failure
        echo $"Another litpd service is currently starting. Exiting"
        return 0
    fi

    # All these should happen with the startup lock held.
    # we check and perform these migration operations if necessary at
    # each service start rather than the (perhaps more natural) rpm
    # postinstall/upgrade time to avoid some complicated interactions
    # with enm_inst upgrade, litp iso import and puppet and yum/rpm.

    if [ "x${LITP_DB_CERT_CHECK}" != xNO ]; then
       __check_db_certs
       retval=$?
       if (( $retval != 0)); then
            echo $"DB cert generation failure. Exiting"
            __release_startup_lock
            return $retval
       fi
    fi

    if [ "x${LITP_DB_AUTO_UPGRADE}" != xNO ]; then
        __autoupgrade
        retval=$?
        if (( $retval != 0)); then
            echo $"DB auto-upgrade failure. Exiting"
            __release_startup_lock
            return $retval
        fi
    fi

    if [ "x${LITP_DB_AUTO_CREATE_DEFAULT_MODEL}" != xNO ]; then
        __automodel
        retval=$?
        if (( $retval != 0)); then
            echo $"Model auto-creation failure. Exiting"
            __release_startup_lock
            return $retval
        fi
    fi

    if [ "x${LITP_DB_CHECK_DB}" != xNO ]; then
        __checkdb
        retval=$?
        if (( $retval != 0)); then
            echo $"DB mismatch. Exiting"
            __release_startup_lock
            return $retval
        fi
    fi

    if [ "x${LITP_DB_CHECK_MODEL}" != xNO ]; then
        __checkmodel
        retval=$?
        if (( $retval != 0)); then
            echo $"Model not found. Exiting"
            __release_startup_lock
            return $retval
        fi
    fi

    mkdir -p $LITP_DIRS
    export PYTHONPATH
    daemon --check $SERVICE $PROCESS --daemonize $CONFIG_ARGS
    retval=$?
    __wait_for_http_unix_socket_server
    __wait_for_http_tcp_server
    __release_startup_lock
    echo
    return $retval
}

__upgradedb() {
    export PYTHONPATH
    python -m litp.data.dbop --action upgrade $CONFIG_ARGS
    return $?
}

__purgedb() {
    export PYTHONPATH
    python -m litp.data.dbop --action purge $CONFIG_ARGS
    return $?
}

upgradedb() {
    echo -n $"Upgrading DB: "
    __acquire_startup_lock
    if (( $? != 0 )); then
        echo_failure
        echo $"litpd service is currently running. Exiting"
        return 1
    fi
    __upgradedb
    retval=$?
    case "$retval" in
        0)
            echo_success
            ;;
        *)
            echo_failure
    esac
    echo
    __release_startup_lock
    return $retval
}

purgedb() {
    echo -n $"Purging DB: "
    __acquire_startup_lock
    if (( $? != 0 )); then
        echo_failure
        echo $"litpd service is currently running. Exiting"
        return 1
    fi
    __purgedb
    retval=$?
    case "$retval" in
        0)
            echo_success
            ;;
        *)
            echo_failure
    esac
    echo
    __release_startup_lock
    return $retval
}

__checkdb() {
    export PYTHONPATH
    python -m litp.data.dbop --action check_pending $CONFIG_ARGS
    return $?
}


checkdb() {
    echo -n $"Checking pending migrations: "
    export PYTHONPATH
    __checkdb
    retval=$?
    case "$retval" in
        0)
            echo -n $"DB is up to date"
            ;;
        $LITP_E_NOTHING_APPLIED)
            echo -n $"DB requires initialisation"
            ;;
        $LITP_E_UPGRADE_REQUIRED)
            echo -n $"DB requires upgrade"
            ;;
        *)
            echo_failure
    esac
    echo
    return $retval
}


__checkmodel() {
    export PYTHONPATH
    python -m litp.data.dbop --action check_model $CONFIG_ARGS
    return $?
}


checkmodel() {
    echo -n $"Checking existing LITP model: "
    export PYTHONPATH
    __checkmodel
    retval=$?
    case "$retval" in
        0)
            echo -n $"LITP model found"
            ;;
        $LITP_E_NO_MODEL)
            echo -n $"No LITP model found"
            ;;
        *)
            echo_failure
    esac
    echo
    return $retval
}

__defaultmodel() {
    export PYTHONPATH
    python -m litp.data.dbop --action default_model $CONFIG_ARGS
    return $?
}


defaultmodel() {
    echo -n $"Creating default model: "
    __acquire_startup_lock
    if (( $? != 0 )); then
        echo_failure
        echo $"litpd service is currently running. Exiting"
        return 1
    fi
    __defaultmodel
    retval=$?
    case "$retval" in
        0)
            echo_success
            ;;
        *)
            echo_failure
    esac
    echo
    __release_startup_lock
    return $retval
}

__autoupgrade() {
    # apply database migrations if necessary
    __checkdb
    retval=$?
    case "$retval" in
        0)
            # DB schema is in sync, no action required
            ;;
        $LITP_E_NOTHING_APPLIED|$LITP_E_UPGRADE_REQUIRED)
            # DB requires migration
            __upgradedb
            retval=$?
            case "$retval" in
            0)
                # DB upgrade okay, proceed
            ;;
            *)
                # Other Error (upgradedb)
                return $retval
            esac
            ;;
        *)
            # Other Error (checkdb)
            return $retval
        esac
    return 0
}


__automodel() {
    # creates a default litp model if no model is present.
    __checkmodel
    retval=$?
    case "$retval" in
        0)
            # a model already exists, no action required
            ;;
        $LITP_E_NO_MODEL)
            # DB exists, but no model apparent in it
            # create our empty model
            __defaultmodel
            retval=$?
            case "$retval" in
                0)
                    # new model created successfully, proceed
                    ;;
                *)
                    # Other Error (defaultmodel)
                    return $retval
            esac
            ;;
        *)
            # Other Error (checkmodel)
            return $retval
    esac
    # everything worked
    return 0
}

__check_db_certs() {

  ${CERT_HEALTHCHECKER} -c
  local retval=$?
  return ${retval}
}

# See how we were called.
case "$1" in
    --start)
        __check_user
        __recreate_pid_file
        start;
        ;;
    --upgradedb)
        __check_user
        upgradedb;
        ;;
    --checkdb)
        __check_user
        checkdb;
        ;;
    --purgedb)
        __check_user
        purgedb;
        ;;
    --checkmodel)
        __check_user
        checkmodel;
        ;;
    --defaultmodel)
        __check_user
        defaultmodel
        ;;
    *)
        echo $"Usage: $0 {--upgradedb|--checkdb|--purgedb|--checkmodel|--defaultmodel}"
        echo $"'Service' is deprecated; Use 'systemctl {start|stop|status|restart|condrestart} litpd.service'"
        exit 2
        ;;
esac
exit $?
