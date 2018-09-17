#!/bin/sh

myname=${0##*/}
path=container-images/tripleo_kolla_template_overrides.j2

grep '{% block' $path |
sort |
uniq -c |
awk -v myname=$myname '
    $1 == 2 {
        printf "%s: found duplicate block for %s\n", myname, $4
        retval=1
    }

    END {exit retval}
'

if [ $? -ne 0 ]; then
    echo "$myname: duplicate jinja block declarations found in $path" >&2
    exit 1
fi
