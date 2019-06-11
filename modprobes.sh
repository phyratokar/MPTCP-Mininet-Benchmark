#!/usr/bin/env bash

if [ "$EUID" -ne 0 ]
  then echo "Please run as root"
  exit
fi


# modprobe all MPTCP CCs

modprobe mptcp_balia
modprobe mptcp_wvegas
modprobe mptcp_olia
modprobe mptcp_coupled