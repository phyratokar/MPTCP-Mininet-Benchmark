from mininet.log import info, error
from mininet.topo import Topo


class MPTopo(Topo):
    """
    Parent abstract class which enables the child topologies to make the hosts mptcp ready.
    IP schema:
        10.0.x.y: where y denotes the host id and x the interface id, e.g. h1-eth0 has 10.0.0.1 and h2-eth2 has 10.0.1.2
    """
    HOST_IP = '10.0.{0}.{1}'
    HOST_MAC = '00:00:00:00:{0:02x}:{1:02x}'
    JITTER = '0.001ms'

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
            host.cmd('ip rule add from {} table {}'.format(ip, i+1))
            host.cmd('ip route add {}/24 dev {} scope link table {}'.format(gateway, intf_name, i+1))
            host.cmd('ip route add default via {} dev {} table {}'.format(gateway, intf_name, i+1))

    def setup_routing(self, net):
        for host in self.hosts():
            self._setup_routing_per_host(net.get(host))


class JsonTopo(MPTopo):
    """
    JSON definition of Topology.
    """
    def build(self, config):
        nodes = {}

        for node in config['nodes']:
            if node['id'].startswith('h'):
                info('Host {} added'.format(node['id']))
                nodes[node['id']] = self.addHost(str(node['id']))
            elif node['id'].startswith('s'):
                info('Switch {} added'.format(node['id']))
                nodes[node['id']] = self.addSwitch(str(node['id']))
            else:
                error('Unknown node type encountered!')
                exit(1)

        for link in config['links']:
            src, dst = link['source'], link['target']
            latency, throughput = link['properties']['latency'], link['properties']['throughput']

            if src not in nodes or dst not in nodes:
                error('Link src or destination does not exist!\t{}<->{}'.format(src, dst))
                exit(1)

            hs, hd = nodes.get(src), nodes.get(dst)
            linkopts = dict(bw=throughput, delay='{}ms'.format(latency), jitter=self.JITTER)
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

