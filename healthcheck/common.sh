#!/bin/bash
set -euxo pipefail
: ${HEALTHCHECK_CURL_MAX_TIME:=10}
: ${HEALTHCHECK_CURL_USER_AGENT:=curl-healthcheck}
: ${HEALTHCHECK_CURL_WRITE_OUT:='\n%{http_code} %{remote_ip}:%{remote_port} %{time_total} seconds\n'}
: ${HEALTHCHECK_CURL_OUTPUT:='/dev/null'}

get_user_from_process() {
    process=$1

    # This helps to capture the actual pids running the process
    pids=$(pgrep -d '|' -f $process)

    # 'cmd' is added to help in case part of the pid is in another pid from
    # another process.
    # $ ps -eo user,pid,cmd
    # USER         PID CMD
    # nova           1 dumb-init --single-child -- kolla_start
    # nova           7 /usr/bin/python2 /usr/bin/nova-conductor
    # nova          25 /usr/bin/python2 /usr/bin/nova-conductor
    # nova          26 /usr/bin/python2 /usr/bin/nova-conductor
    # root        8311 ps -eo user,pid,cmd
    # The following "ps" command will capture the user from PID 7 which
    # is safe enough to assert this is the user running the process.
    ps -eo user,pid,cmd | grep $process | grep -E $pids | awk 'NR==1{print $1}'
}

healthcheck_curl () {
    if [ $# == 0 ]; then
        echo 'healthcheck_curl: no parameter provided'
        return 1
    fi
    export NSS_SDB_USE_CACHE=no
    curl -g -k -q -s -S --fail -o "${HEALTHCHECK_CURL_OUTPUT}" \
        --max-time "${HEALTHCHECK_CURL_MAX_TIME}" \
        --user-agent "${HEALTHCHECK_CURL_USER_AGENT}" \
        --write-out "${HEALTHCHECK_CURL_WRITE_OUT}" \
        "$@" || return 1
}

healthcheck_port () {
    process=$1

    shift 1
    args=$@
    puser=$(get_user_from_process $process)
    ports=${args// /|}
    pids=$(pgrep -d '|' -f $process)
    # https://bugs.launchpad.net/tripleo/+bug/1843555
    # "ss" output is different if run as root vs as the user actually running
    # the process. So we also verify that the process is connected to the
    # port by using "sudo -u" to get the right output.
    # Note: the privileged containers have the correct ss output with root
    # user; which is why we need to run with both users, as a best effort.
    # https://bugs.launchpad.net/tripleo/+bug/1860556
    # do ot use "-q" option for grep, since it returns 141 for some reason with
    # set -o pipefail.
    # See https://stackoverflow.com/questions/19120263/why-exit-code-141-with-grep-q
    (ss -ntuap; sudo -u $puser ss -ntuap) | sort -u | grep -E ":($ports).*,pid=($pids),">/dev/null
}

healthcheck_listen () {
    process=$1

    shift 1
    args=$@
    ports=${args// /|}
    pids=$(pgrep -d '|' -f $process)
    ss -lnp | grep -qE ":($ports).*,pid=($pids),"
}

healthcheck_socket () {
    process=$1
    socket=$2

    # lsof truncate command name to 15 characters and this behaviour
    # cannot be disabled
    if [ ${#process} -gt 15 ] ; then
        process=${process:0:15}
    fi
    lsof -Fc -Ua $socket | grep -q "c$process"
}

healthcheck_file_modification () {
    file_path=$1
    limit_seconds=$2

    # if the file doesn't exist, return 1
    if [ ! -f $file_path ]; then
        echo "${file_path} does not exist for file modification check"
        return 1
    fi
    curr_time=$(date +%s)
    last_mod=$(stat -c '%Y' $file_path)
    limit_epoch=$(( curr_time-limit_seconds ))
    if [ ${limit_epoch} -gt ${last_mod} ]; then
        return 1
    fi
}

get_config_val () {
    crudini --get "$1" "$2" "$3" 2> /dev/null || echo "$4"
}

# apachectl -S is slightly harder to parse and doesn't say if the vhost is serving SSL
get_url_from_vhost () {
    vhost_file=$1
    if test -n "${vhost_file}" && test -r "${vhost_file}" ; then
        server_name=$(awk '/ServerName/ {print $2}' $vhost_file)
        ssl_enabled=$(awk '/SSLEngine/ {print $2}' $vhost_file)
        bind_port=$(grep -h "<VirtualHost .*>" $vhost_file | sed 's/<VirtualHost .*:\(.*\)>/\1/')
        wsgi_alias=$(awk '/WSGIScriptAlias/ {print $2}' $vhost_file)
        proto=http
        if [[ $ssl_enabled == "on" ]]; then
            proto=https
        fi
        if [[ $wsgi_alias != "/" ]]; then
            wsgi_alias="${wsgi_alias}/"
        fi
        echo ${proto}://${server_name}:${bind_port}${wsgi_alias}
    else
        exit 1
    fi
}

check_swift_interval () {
    service=$1
    if ps -e | grep --quiet swift-$service; then
        interval=$(get_config_val $conf $service interval 300)
        last=`grep -o "\"replication_last\": [0-9]*" $cache | cut -f 2 -d " "`
        now=`date +%s`
        if [ `expr $now - $last` -gt $interval ]; then
            echo "Last replication run did not finish within interval of $interval seconds."
            exit 1
        fi
    fi
}

# Wrap an IPv6 address in square brackets if not already wrapped
wrap_ipv6 () {
    ip=$1

    if [[ $ip =~ ":" ]] && [[ $ip != *\] ]]; then
        echo [$ip]
    else
        echo $ip
    fi
}
