import math

from mininet.log import info, warn, error
from mininet.topo import Topo


class MPTopo(Topo):
    """
    Parent abstract class which enables the child topologies to make the hosts mptcp ready.
    IP schema:
        10.0.x.y: where y denotes the host id and x the interface id, e.g. h1-eth0 has 10.0.0.1 and h2-eth2 has 10.0.1.2
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

            # Setup routing tables to so the kernel routes different source addresses through different interfaces.
            # See http://multipath-tcp.org/pmwiki.php/Users/ConfigureRouting for information
            host.cmd('ip rule add from {} table {}'.format(ip, i + 1))
            host.cmd('ip route add {}/24 dev {} scope link table {}'.format(gateway, intf_name, i + 1))
            host.cmd('ip route add default via {} dev {} table {}'.format(gateway, intf_name, i + 1))

    def setup_routing(self, net):
        for host in self.hosts():
            self._setup_routing_per_host(net.get(host))


class JsonTopo(MPTopo):
    """
    JSON definition of Topology.
    """
    zero_warning_given = False

    @staticmethod
    def calculate_queue_size(rtt, rate, multiplier=1.5, mtu=1500, added_pkts=20):
        """
        Size of queue (number of packets) according to rule of thumb where the bottleneck buffer should hold at least
        one BDP worth of packets. Multiply the BDP by a small factor to ensure even a single flow can fully utilize the
        bottleneck. Adding a small number of packets to the result enables ultra low delay networks and links to
        function properly.
        => B = multiplier * (RTT * Rate) + n_pkts_added

        :param rtt:         RTT time in ms
        :param rate:        bottleneck rate in Mbps
        :param multiplier:  factor by which bdp is multiplied (should be > 1 to account for tcp/ip header and timeouts)
        :param mtu:         pkt size in bytes
        :param added_pkts:  number of packets to add to buffer size
        :return:            number of packets in bottleneck buffer
        """
        rate_Bps = 1e6 * (rate / 8)
        rtt_seconds = rtt / 1000.0
        bdp_pkt = rtt_seconds * rate_Bps / mtu
        return int(math.ceil(multiplier * bdp_pkt + added_pkts))

    def build(self, config):
        nodes = {}

        # Add Hosts and Switches
        for node in config['nodes']:
            if node['id'].startswith('h'):
                info('Host {} added\n'.format(node['id']))
                nodes[node['id']] = self.addHost(str(node['id']))
            elif node['id'].startswith('s'):
                info('Switch {} added\n'.format(node['id']))
                nodes[node['id']] = self.addSwitch(str(node['id']))
            else:
                error('Unknown node type encountered!\n')
                exit(1)

        # Add links
        for link in config['links']:
            src, dst = link['source'], link['target']
            latency, bandwidth = link['properties']['latency'], link['properties']['bandwidth']

            # check if link config is valid
            if src not in nodes or dst not in nodes:
                error('Link src or destination does not exist! \t{}<->{}\n'.format(src, dst))
                exit(1)
            if latency < 0:
                error('Link has latency smaller than 0! \t{}<->{}\n'.format(src, dst))
                exit(1)
            elif latency == 0 and not self.zero_warning_given:
                self.zero_warning_given = True
                warn('Attention, working with "{}ms" delay in topologies where there are links with some delay can '
                     'yield unexpected results! As a precaution "0ms" is changed to "0.1ms"\n'.format(latency))

            hs, hd = nodes.get(src), nodes.get(dst)
            latency = latency if latency > 1 else 0.1

            # Note: Assumption here is that only the bottleneck link notably contributes to the rtt! If that's not the
            #       case, the buffers on the bottleneck links are too small to fully utilize the path. Furthermore do
            #       non-bottleneck links get a small fixed size buffer (~20 pkts) which should be enough to saturate the
            #       bottlenecks as long as the links have a large enough rate compared to the bottleneck.
            q_size = self.calculate_queue_size(rtt=2 * latency, rate=bandwidth)

            linkopts = dict(bw=bandwidth, delay='{}ms'.format(latency), jitter='0ms', max_queue_size=q_size)
            self.addLink(hs, hd, **linkopts)
            info('Link added {}-{}, options {}\n'.format(hs, hd, linkopts))

        # print('\n'.join(['{} <-> {}, \tlatency: {}, \tbandwidth: {}Mbps'
        #                 .format(s, d, c['delay'], c['bw']) for s, d, c in self.links(sort=True, withInfo=True)]))


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
        linkopts = dict(bw=10, delay='2ms')
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
