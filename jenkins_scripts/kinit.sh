#!/bin/bash

# if in IPv6 Only Environment, uncomment and use the following line
url="$PF_URL/$PF_NAME?t=$PF_KEY"
get_keytab() {
        res=`curl -sL -m 5 -w "%{http_code}" -o pf.keytab $url`
        if [ $res -ne 200 ]; then
                echo get keytab file error,code=$res
                exit 1
        fi
        KRB5CCNAME="$krb5file" kinit -k -t pf.keytab $PF_NAME
}

if [ -f pf.keytab ]; then
        KRB5CCNAME="$krb5file" kinit -k -t pf.keytab $PF_NAME
        if [ $? -eq 1 ]; then
                get_keytab
        fi
else
        get_keytab
fi