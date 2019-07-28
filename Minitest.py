import os
import time

from mininet.cli import CLI
from mininet.net import Mininet
from mininet.topo import Topo
from mininet.link import TCLink


class MPTopo(Topo):
    """
    Parent abstract class which enables the child topologies to make the hosts mptcp ready.
    """
    HOST_IP = '10.0.{0}.{1}'
    HOST_MAC = '00:00:00:00:{0:02x}:{1:02x}'

    def _setup_routing_per_host(self, host):
        # Manually set the ip addresses of the interfaces
        host_id = int(host.name[1:])

        for i, intf_name in enumerate(host.intfNames()):
            ip = self.HOST_IP.format(i, host_id)
            gateway = self.HOST_IP.format(i, 0)
            mac = self.HOST_MAC.format(i, host_id)

            # set IP and MAC of host
            host.intf(intf_name).config(ip='{}/24'.format(ip), mac=mac)

            ## Setup routing tables to so the kernel routes different source addresses through different interfaces.
            ## See http://multipath-tcp.org/pmwiki.php/Users/ConfigureRouting for information
            # host.cmd('ip rule add from {} table {}'.format(ip, i+1))
            # host.cmd('ip route add {}/24 dev {} scope link table {}'.format(gateway, intf_name, i+1))
            # host.cmd('ip route add default via {} dev {} table {}'.format(gateway, intf_name, i+1))

    def setup_routing(self, net):
        for host in self.hosts():
            self._setup_routing_per_host(net.get(host))


class SingleMPFlowTopo(MPTopo):
    """
      /--- s1 --- s2 ---\
    h1                  h2
      \--- s3 --- s4 ---/
    """

    def build(self, bw_restriction_on_first_leg):
        # Add hosts and switches
        h1 = self.addHost('h1')
        h2 = self.addHost('h2')
        s1 = self.addSwitch('s1')
        s2 = self.addSwitch('s2')
        s3 = self.addSwitch('s3')
        s4 = self.addSwitch('s4')

        # Add links
        if bw_restriction_on_first_leg:
            print('Adding bw restriction to first leg')
            self.addLink(h1, s1, bw=10)  # , delay='0ms', jitter='0.25ms')
            self.addLink(h1, s3, bw=10)  # , delay='0ms', jitter='0.25ms')

        else:
            print('NOT adding bw restriction to first leg')
            self.addLink(h1, s1)  # , delay='0ms', jitter='0.25ms')
            self.addLink(h1, s3)  # , delay='0ms', jitter='0.25ms')

        self.addLink(s1, s2, bw=10, delay='50ms')
        self.addLink(s3, s4, bw=10, delay='50ms')

        self.addLink(s2, h2)
        self.addLink(s4, h2)


def main():
    # Making sure MPTCP is enabled on system and congestion control algorithm modules are loaded
    os.system('modprobe mptcp_balia; modprobe mptcp_wvegas; modprobe mptcp_olia; modprobe mptcp_coupled')
    os.system('sysctl -w net.mptcp.mptcp_enabled=1')
    os.system('sysctl -w net.mptcp.mptcp_path_manager=fullmesh')
    os.system('sysctl -w net.mptcp.mptcp_scheduler=default')

    for bw_on_first_leg in [True, False]:
        # Start Mininet
        topo = SingleMPFlowTopo(bw_restriction_on_first_leg=bw_on_first_leg)
        net = Mininet(topo=topo, link=TCLink)

        # make sure every host has two IPs assigned
        topo.setup_routing(net)

        net.start()
        time.sleep(1)

        # Test throughput for different configurations
        for cc in ['lia', 'olia', 'balia', 'wvegas']:
            print('\n#### Testing bandwidth for {} (restriction on first leg: {})####'.format(cc, bw_on_first_leg))

            # set congestion control algoritm
            os.system('sysctl -w net.ipv4.tcp_congestion_control={}'.format(cc))

            # test bandwidth between the two hosts
            src = net.get('h1')
            dst = net.get('h2')
            serverbw, _clientbw = net.iperf([src, dst], seconds=10)
            # print('BW on Server: {}'.format(serverbw))

        # CLI(net)

        net.stop()


if __name__ == '__main__':
    try:
        main()
    except:
        print("-"*80)
        import traceback
        traceback.print_exc()
        os.system("killall -9 top bwm-ng tcpdump cat mnexec iperf iperf3; mn -c")
