#!/usr/bin/env bash

if [ $(id -u) -ne 0 ];
  then echo "Please run as root"
  exit
fi


# modprobe all MPTCP CCs and activate to update net.ipv4.tcp_allowed_congestion_control

modprobe mptcp_balia
sysctl -w net.ipv4.tcp_congestion_control=balia
modprobe mptcp_wvegas
sysctl -w net.ipv4.tcp_congestion_control=wvegas
modprobe mptcp_olia
sysctl -w net.ipv4.tcp_congestion_control=olia
modprobe mptcp_coupled
sysctl -w net.ipv4.tcp_congestion_control=lia
sysctl -w net.ipv4.tcp_congestion_control=cubic