# MPTCP Mininet Benchmarking tool


## Getting started on a Ubuntu Server

These instructions should get you started on a Ubuntu server instance.
Specifically we used Ubuntu server 18.04, [MPTCP](http://multipath-tcp.org/) kernel v0.95, and [Mininet](http://mininet.org/) v2.3.0d6.
First install the MPTCP kernel on the machine, either using the apt repository or compiling the kernel yourself.
More information about installing the MPTCP kernel can be fund [here](http://multipath-tcp.org/pmwiki.php/Users/HowToInstallMPTCP?).
Similar instructions about how to install Mininet can be found [here](http://mininet.org/download/).

### Install apt repository kernel
Installing the kernel from the apt repository is the simplest method and only takes a couple of minutes.
```
sudo apt update
sudo apt-key adv --keyserver hkp://keys.gnupg.net --recv-keys 379CE192D401AB61
sudo sh -c "echo 'deb https://dl.bintray.com/cpaasch/deb stretch main' > /etc/apt/sources.list.d/mptcp.list"
sudo apt-get update
sudo apt-get install linux-mptcp -y

# after rebooting check if mptcp is installed
sudo dmsg | grep MPTCP
```

### Compile the kernel yourself
Compiling the kernel yourself allows you to change certain aspects of the kernel or specify that the MPTCP congestion control algorithms should be loaded per default and not as modules.
Note that the compilation can take a long period of time, depending on the system.
The `-j` parameter during `make` makes the compilation run in parallel and speed it up.

```
git clone --depth=1 git://github.com/multipath-tcp/mptcp.git
cd mptcp
make menuconfig
make -j $(nproc)
sudo make modules_install
sudo make install
sudo reboot

# after rebooting check if mptcp is installed
sudo dmsg | grep MPTCP
```

### Mininet installation
To install Mininet, simply clone the repository and use the convenience script Mininet provides.

```
cd
git clone git://github.com/mininet/mininet
cd mininet
git checkout -b 2.3.0d6 2.3.0d6
cd ..
./mininet/util/install.sh -a
```

## Running MPTCP Mininet experiments
After installing the MPTCP kernel and Mininet, the system should be able to run MPTCP experiments.
Note that if the MPTCP congestion control algorithms are modules and not loaded, you need to use `modprobe` to make them available.
Eg. `sudo modprobe mptcp_coupled` to load LIA.

After loading the necessary modules, the benchmark can be run with the following command:

```
sudo python main.py --run de --topo two_paths
```