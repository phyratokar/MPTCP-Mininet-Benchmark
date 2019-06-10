"""Custom topology example

Two directly connected switches plus a host for each switch:

   host --- switch --- switch --- host

Adding the 'topos' dict with a key/value pair to generate our newly defined
topology enables one to pass in '--topo=mytopo' from the command line.


Hosts need to be names 'hx' where x is a number ('h1', 'h33', etc).

IP schema:
    10.0.x.y    where y denotes the host id and x the interface id, i.e. h1-eth0 has 10.0.0.1 and h2-eth2 has 10.0.1.2
"""

from mininet.topo import Topo
from mininet.net import Mininet
from mininet.cli import CLI
from mininet.node import CPULimitedHost
from mininet.link import TCLink
from mininet.util import dumpNodeConnections
from mininet.log import setLogLevel

from subprocess import Popen, PIPE
import os

HOST_IP = '10.0.{0}.{1}'
HOST_MAC = '00:00:00:00:{0:02x}:{1:02x}'


class MPTopo(Topo):
    """
    Parent abstract class which enables the child topologies to make the hosts mptcp ready.
    """
    @staticmethod
    def _setup_routing_per_host(host):
        # Manually set the ip addresses of the interfaces
        host_id = int(host.name[1:])

        for i, intf_name in enumerate(host.intfNames()):
            ip = HOST_IP.format(i, host_id)
            gateway = HOST_IP.format(i, 0)
            mac = HOST_MAC.format(i, host_id)

            # set IP and MAC of host
            host.intf(intf_name).config(ip='{}/24'.format(ip), mac=mac)

            # Setup routing tables to so the kernel routes different source addresses through different interfaces.
            # See http://multipath-tcp.org/pmwiki.php/Users/ConfigureRouting for information
            host.cmd('ip rule add from {} table {}'.format(ip, i+1))
            host.cmd('ip route add {}/24 dev {} scope link table {}'.format(gateway, intf_name, i+1))
            host.cmd('ip route add default via {} dev {} table {}'.format(gateway, intf_name, i+1))

    def setup_routing(self, net):
        for host in self.hosts():
            self._setup_routing_per_host(net.get(host))
            print(host)


class SharedLinkTopo(MPTopo):
    """
    h1        h2
     \        /
      s1 --- s2
     /        \
    h3        h4
    """

    def build(self):
        # Add hosts and switches
        h1 = self.addHost('h1')
        h2 = self.addHost('h2')
        h3 = self.addHost('h3')
        h4 = self.addHost('h4')
        s1 = self.addSwitch('s1')
        s2 = self.addSwitch('s2')

        # Add links
        # , loss=10, max_queue_size=1000, use_htb=True
        linkopts = dict(bw=100, delay='2ms')
        self.addLink(h1, s1, **linkopts)
        self.addLink(h3, s1, **linkopts)

        self.addLink(s1, s2, **linkopts)

        self.addLink(s2, h2, **linkopts)
        self.addLink(s2, h4, **linkopts)


class SingleMPFlowTopo(MPTopo):
    """
      /--- s1 --- s2 ---\
    h1                  h2
      \--- s3 --- s4 ---/
    """

    def build(self):
        # Add hosts and switches
        h1 = self.addHost('h1')
        h2 = self.addHost('h2')
        s1 = self.addSwitch('s1')
        s2 = self.addSwitch('s2')
        s3 = self.addSwitch('s3')
        s4 = self.addSwitch('s4')

        # Add links
        # , loss=10, max_queue_size=1000, use_htb=True
        linkopts = dict(bw=10, delay='1ms')
        linkopts_slow = dict(bw=10, delay='2ms')
        self.addLink(h1, s1, **linkopts_slow)
        self.addLink(h1, s3, **linkopts)

        self.addLink(s1, s2, **linkopts_slow)
        self.addLink(s3, s4, **linkopts)

        self.addLink(s2, h2, **linkopts_slow)
        self.addLink(s4, h2, **linkopts)


class MPagainstSPTopo(MPTopo):
    """
      /--- s1 --- s2 ---\
    h1                   h2
      \--- s3 --- s4 ---/
           /       \
          h3       h4
    """

    def build(self):
        # Add hosts and switches
        h1 = self.addHost('h1')
        h2 = self.addHost('h2')
        h3 = self.addHost('h3')
        h4 = self.addHost('h4')
        s1 = self.addSwitch('s1')
        s2 = self.addSwitch('s2')
        s3 = self.addSwitch('s3')
        s4 = self.addSwitch('s4')

        # Add links
        # , loss=10, max_queue_size=1000, use_htb=True
        linkopts = dict(bw=10, delay='1ms')
        self.addLink(h1, s1, **linkopts)
        self.addLink(h1, s3, **linkopts)
        self.addLink(h3, s3, **linkopts)

        self.addLink(s1, s2, **linkopts)
        self.addLink(s3, s4, **linkopts)

        self.addLink(s2, h2, **linkopts)
        self.addLink(s4, h2, **linkopts)
        self.addLink(s4, h4, **linkopts)


topos = {'mytopo': (lambda: SingleMPFlowTopo())}

