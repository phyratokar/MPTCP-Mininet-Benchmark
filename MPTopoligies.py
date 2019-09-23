import math
import itertools
import os

from mininet.log import info, warn, error
from mininet.net import Mininet
from mininet.topo import Topo

import utils


class MPMininetWrapper(Mininet):
    """
    Wrapper around Mininet to enable make hosts MPTCP ready by setting IP addresses and setting up routing.
    IP schema:
        10.0.x.y: where y denotes the host id and x the interface id, e.g. h1-eth0 has 10.0.0.1 and h2-eth2 has 10.0.1.2
    """
    HOST_IP = '10.0.{0}.{1}'
    HOST_MAC = '00:00:00:00:{0:02x}:{1:02x}'

    def __init__(self, *args, **kwargs):
        super(MPMininetWrapper, self).__init__(*args, **kwargs)
        self.setup_routing()

    def setup_routing(self):
        """
        Set IP and MAC address for each interface on each host.
        :return:    None
        """
        for host in self.hosts:
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


class MPTopo(Topo):
    """
    Parent abstract class which serves as a template for the child topologies.
    """

    def __init__(self, *args, **kwargs):
        self.host_pairings, self.host_cc = None, None
        super(MPTopo, self).__init__(*args, **kwargs)

    def get_topo_name(self):
        """ Override this method, giving the topology a name """
        if self.get_topo_name.im_func == MPTopo.get_topo_name.im_func:
            raise NotImplementedError('Topologies must implement get_topo_name')

    def get_host_pairings(self):
        """ Override this method, specifying the client-server pairs """
        if self.get_host_pairings.im_func == MPTopo.get_host_pairings.im_func:
            raise NotImplementedError('Topologies must implement get_host_pairings')

    def get_ccs_per_host(self):
        """ Override this method, specifying which host runs what congestion control """
        if self.get_ccs_per_host.im_func == MPTopo.get_ccs_per_host.im_func:
            raise NotImplementedError('Topologies must implement get_ccs_per_host')

    def get_logs_dir(self):
        """ Override this method, specifying the subfolder path where to store logfiles """
        if self.get_logs_dir.im_func == MPTopo.get_logs_dir.im_func:
            raise NotImplementedError('Topologies must implement get_logs_dir')

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
        rate_bps = 1e6 * (rate / 8)
        rtt_seconds = rtt / 1000.0
        bdp_pkt = rtt_seconds * rate_bps / mtu
        return int(math.ceil(multiplier * bdp_pkt + added_pkts))


class JsonTopo(MPTopo):
    """
    Build Minient Topology from JSON definition.
    """
    def __init__(self, *args, **kwargs):
        self.zero_warning_given = False
        self.json_config = None
        super(JsonTopo, self).__init__(*args, **kwargs)

    def get_topo_name(self):
        return self.json_config['topology_id']

    def build(self, config):
        """
        Given JSON definition of topology, build a Mininet network.
        :param config:  JSON config
        :return:        None
        """
        self.json_config = config
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

        self._set_host_pairings()
        # print('\n'.join(['{} <-> {}, \tlatency: {}, \tbandwidth: {}Mbps'
        #                 .format(s, d, c['delay'], c['bw']) for s, d, c in self.links(sort=True, withInfo=True)]))

    def get_host_pairings(self):
        return self.host_pairings

    def get_ccs_per_host(self):
        return self.host_cc

    def get_logs_dir(self):
        cc_dir = '_'.join(self.get_ccs_per_host().values())
        delay_dir = '_'.join(['{}ms'.format(float(delay)) for _, delay in utils.get_group_with_value(self.json_config, 'latency')])
        bw_dir = '_'.join(['{}Mbps'.format(int(rate)) for _, rate in utils.get_group_with_value(self.json_config, 'bandwidth')])
        return os.path.join(self.get_topo_name(), cc_dir, bw_dir, delay_dir)

    def _set_host_pairings(self):
        """
        Read pairings from JSON config, which clients talks to which server with what congestion control algorithm.
        Note: Assumption is that only senders set a congestion control scheme
        """
        pairs, ccs = [], []
        for node in [node for node in self.json_config['nodes'] if node['id'].startswith('h')]:
            if 'server' in node['properties']:
                assert('cc' in node['properties'])
                pairs.append((str(node['id']), str(node['properties']['server'])))
                ccs.append(str(node['properties']['cc']))

        # sort the lists alphabetically (sort by client/server pairs)
        zipped_list = sorted(zip(pairs, ccs))
        ccs = [cc for _, cc in zipped_list]
        pairs = [pair for pair, _ in zipped_list]

        # make sure every host is included in some connection and all mininet hosts are utilized
        hosts = list(itertools.chain.from_iterable(pairs))
        json_hosts = [n for n in self.json_config['nodes'] if n['id'].startswith('h')]
        assert all(n['id'] in hosts for n in json_hosts), \
            'Host {} not contained in any host pairings!\n'.format(map(lambda x: x['id'], json_hosts))
        assert all(h in hosts for h in self.hosts()), \
            'Host {} not contained in any host pairings!\n'.format(self.hosts())
        assert all(cc in utils.get_system_available_congestioncontrol_algos() for cc in ccs), \
            'Congestion Control algorithm not allowed by sysctl! Tried to use {}.\n'.format(', '.join(ccs))
        assert(len(pairs) == len(ccs)), \
            'JSONTopo._set_host_pairings(): Unequal number of paris and congestion control names.\n'

        self.host_pairings = pairs
        self.host_cc = {h[0]: cc for h, cc in zip(pairs, ccs)}


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
