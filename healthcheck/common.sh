#!/bin/bash
set -euo pipefail
: ${HEALTHCHECK_DEBUG:=0}
if [ $HEALTHCHECK_DEBUG -ne 0 ]; then
    set -x
    exec 3>&1
else
    exec 3>/dev/null
fi
: ${HEALTHCHECK_CURL_MAX_TIME:=10}
: ${HEALTHCHECK_CURL_USER_AGENT:=curl-healthcheck}
: ${HEALTHCHECK_CURL_PY_USER_AGENT:=pyrequests-healthcheck}
: ${HEALTHCHECK_CURL_WRITE_OUT:='\n%{http_code} %{remote_ip}:%{remote_port} %{time_total} seconds\n'}
: ${HEALTHCHECK_CURL_OUTPUT:='/dev/null'}

get_user_from_process() {
    process=$1

    # This helps to capture the actual pid running the process
    pid=$(pgrep -d ',' -f $process)

    # Here, we use the embedded `ps' filter capabilities, and remove the
    # output header. We ensure we get the user for the selected PIDs only.
    # In order to ensure we don't get multiple lines, we truncate it with `head'
    ps -h -q${pid} -o user | head -n1
}

healthcheck_curl () {
    if [ $# == 0 ]; then
        echo 'healthcheck_curl: no parameter provided'
        return 1
    fi
    export NSS_SDB_USE_CACHE=no
    if [ -n "${HEALTHCHECK_CURL_PY+x}" ] || [ -n "${no_proxy+x}" ] || [ -n "${NO_PROXY+x}" ]; then
        ${HEALTHCHECK_SCRIPTS:-/usr/share/openstack-tripleo-common/healthcheck}/http-healthcheck.py \
        --max-time "${HEALTHCHECK_CURL_MAX_TIME}" \
        --user-agent "${HEALTHCHECK_CURL_PY_USER_AGENT}" \
        --write-out "${HEALTHCHECK_CURL_WRITE_OUT}" \
        "$@" || return 1
    else
        curl -g -k -q -s -S --fail -o "${HEALTHCHECK_CURL_OUTPUT}" \
        --max-time "${HEALTHCHECK_CURL_MAX_TIME}" \
        --user-agent "${HEALTHCHECK_CURL_USER_AGENT}" \
        --write-out "${HEALTHCHECK_CURL_WRITE_OUT}" \
        "$@" || return 1
    fi
}

healthcheck_port () {
    process=$1

    shift 1
    ports=""
    # First convert port to hex value. We need to 0-pad it in order to get the
    # right format (4 chars).
    for p in $@; do
        ports="${ports}|$(printf '%0.4x' $p)"
    done
    # Format the string - will be ":(hex1|hex2|...)"
    ports=":(${ports:1})"
    # Parse the files. We need to extract only one value (socket inode) based on the matching port. Let's check local and target for establised connection.
    # Line example:
    # 534: DE0D10AC:1628 DE0D10AC:8B7C 01 00000000:00000000 02:000000D3 00000000 42439        0 574360 2 0000000000000000 20 4 0 10 -1
    #              |             |                                                                |
    #      $2 local connection   |                                                            $10 Socket inode
    #                   $3 Connection target
    # Using the main /proc/net/{tcp,udp} allow to take only the connections existing in the current container. If we were using /proc/PID/net/{tcp,udp}, we
    # would get all the connections existing in the same network namespace as the PID. Since we're using network=host, that would show *everything*.
    # the "join" method is weird, and fails if the array is empty.
    # Note: join comes from gawk's /usr/share/awk/join.awk and has some weird parameters.
    sockets=$(awk -i join -v m=${ports} '{IGNORECASE=1; if ($2 ~ m || $3 ~ m) {output[counter++] = $10} } END{if (length(output)>0) {print join(output, 0, length(output)-1, "|")}}' /proc/net/{tcp,udp,tcp6,udp6})

    # If no socket, just fail early
    test -z $sockets && exit 1
    match=0
    for pid in $(pgrep -f $process); do
        # Here, we check if a socket is actually associated to the process PIDs
        match=$(( $match+$(find /proc/$pid/fd/ -ilname "socket*" -printf "%l\n" 2>/dev/null | grep -c -E "(${sockets})") ))
        test $match -gt 0 && exit 0 # exit as soon as we get a match
    done
    exit 1 # no early exit, meaning failure.
}

healthcheck_listen () {
    process=$1

    shift 1
    args=$@
    ports=${args// /,}
    pids=$(pgrep -d ',' -f $process)
    lsof -n -w -P -a -p${pids} -iTCP:${ports} -s TCP:LISTEN >&3 2>&1
}

healthcheck_socket () {
    process=$1
    socket=$2
    pids=$(pgrep -d ',' -f $process)

    lsof -n -Fc -Ua -p${pids} $socket >&3 2>&1
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
        wsgi_alias=$(awk '/WSGIScriptAlias / {print $2; exit}' $vhost_file)
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
    if ps -ef | grep --quiet [s]wift-${service} >&3 2>&1; then
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
