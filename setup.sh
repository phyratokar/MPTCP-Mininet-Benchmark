#!/usr/bin/env bash

if [ "$EUID" -ne 0 ]
  then echo "Please run as root"
  exit
fi


apt-key adv --keyserver hkp://keys.gnupg.net --recv-keys 379CE192D401AB61
sh -c "echo 'deb https://dl.bintray.com/cpaasch/deb stretch main' > /etc/apt/sources.list.d/mptcp.list"
apt-get update
apt-get install linux-mptcp -y


git clone git://github.com/mininet/mininet
cd mininet
git checkout -b 2.2.2 2.2.2
cd ..
sh ./mininet/util/install.sh -a

apt-get install iperf3 tcpdump

echo "Please reboot the system to enable the mptcp kernel, Mininet should be installed and working."
