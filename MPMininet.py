import json

from mininet.topo import Topo
from mininet.net import Mininet
from mininet.cli import CLI
from mininet.node import CPULimitedHost
from mininet.link import TCLink
from mininet.util import dumpNodeConnections, errRun, errFail
from mininet.log import setLogLevel, error, info
import shlex

from subprocess import Popen, PIPE
import os
from argparse import ArgumentParser

from MPTopolies import SingleMPFlowTopo, SharedLinkTopo, MPagainstSPTopo, MPTopo, JsonTopo


class MPMininet:
    """Create and run multiple link network"""
    def __init__(self):
        self.net = None
        self.out_folder = './logs/'
        self.config = None
        self.topology = None
        self.congestion_control = None

    def get_net(self):
        return self.net

    def read_json(self, file_name):
        if not os.path.isfile(file_name):
            error('JSON topology file not found! {}'.format(file_name))
            exit(1)

        with open(file_name, 'r') as f:
            config = json.loads(f.read())

        if config is None:
            error('Config not found')
        self.config = config

    @staticmethod
    def _set_system_variable(var, value):
        errFail(['sysctl', '-w', '{0}={1}'.format(var, value)])
        out, err, ret = errFail(['sysctl', '-n', var])
        info('type {} and value "{}"'.format(type(out), out))
        out = out.replace('\n', '')
        if type(value) is bool and bool(out) != value or type(value) is not bool and out != value:
            raise Exception("sysctl Fail: setting {} failed, should be {} is {}".format(var, value, out))

    @staticmethod
    def set_system_variables(mptcp, cc):
        # Setting up MPTCP
        MPMininet._set_system_variable('net.mptcp.mptcp_enabled', mptcp)

        # Congestion control
        MPMininet._set_system_variable('net.ipv4.tcp_congestion_control', cc)

    def start(self, topology_name, congestion_control):
        self.topology = topology_name
        self.congestion_control = congestion_control

        self.set_system_variables(mptcp=True, cc=congestion_control)

        self.read_json('topologies/' + topology_name + '.json')

        topo = JsonTopo(self.config)

        # add host=CPULimitedHost if applicable
        self.net = Mininet(topo=topo, link=TCLink)
        topo.setup_routing(self.net)
        self.net.start()

    def get_iperf_pairings(self):
        pairs = []
        for node in [node for node in self.config['nodes'] if node['id'].startswith('h')]:
            if 'server' in node['properties']:
                pairs.append((str(node['id']), str(node['properties']['server'])))
        return pairs

    def get_variable_links(self):
        return [link for link in self.config['links'] if 'latency_tests' in link['properties']]

    def start_custom_code(self, host_pairs, ):
        folder = self.out_folder + '{}/{}/{}ms-{}ms/'.format(self.topology, self.congestion_control, )
        os.makedirs(folder, exist_ok=True)

        server_command = 'python receiver.py -p 5001 -o '

    def run(self):
        iperf_pairs = self.get_iperf_pairings()
        variable_links = self.get_variable_links()

        host_pairs = map(lambda x: (self.net.get(x[0]), self.net.get(x[1])), iperf_pairs)


        h1, h2 = self.net.get('h1', 'h2')
        print("Running client and server")

        # server_command = 'python receiver.py -p 5001 -o {}-{}-rcv{}.txt'.format(args.cc, args.topo, 2)
        # server_args = shlex.split(server_command)
        # server = h2.popen(server_args)
        # client_command = 'python sender.py -s 10.0.0.2 -p 5001 -o {}-{}-snd{}.txt -t {}'.format(args.cc, args.topo, 1, 30)
        # client_args = shlex.split(client_command)
        # client = h1.popen(client_args)
        # client.wait()
        # server.wait()
        #
        # print('Done with experiments.\n' + '-'*80 + '\n')

    def stop(self):
        self.net.stop()
