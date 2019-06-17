import json
import time

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
    def __init__(self, json_config, congestion_control, delay_name, start_cli=False):
        self.config = json_config
        self.congestion_control = congestion_control
        self.delay_name = delay_name
        self.topology = json_config['topology_id']
        self.net = None
        self.out_folder = './logs'
        self.start(start_cli)

    def start(self, cli):
        self.set_system_variables(mptcp=True, cc=self.congestion_control)

        topo = JsonTopo(self.config)

        # add host=CPULimitedHost if applicable
        self.net = Mininet(topo=topo, link=TCLink)
        topo.setup_routing(self.net)
        self.net.start()

        if cli:
            CLI(self.net)

        self.run()

        # CLI(self.net)
        self.net.stop()

    def get_net(self):
        return self.net

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

    def get_iperf_pairings(self):
        pairs = []
        for node in [node for node in self.config['nodes'] if node['id'].startswith('h')]:
            if 'server' in node['properties']:
                pairs.append((str(node['id']), str(node['properties']['server'])))
        mininet_host_pairs = map(lambda x: (self.net.get(x[0]), self.net.get(x[1])), pairs)
        return mininet_host_pairs

    def start_custom_code(self, host_pairs, ):
        folder = self.out_folder + '{}/{}/{}ms-{}ms/'.format(self.topology, self.congestion_control, )
        os.makedirs(folder, exist_ok=True)

        server_command = 'python receiver.py -p 5001 -o '

    def run(self):
        iperf_pairs = self.get_iperf_pairings()
        print("Running client and server")

        folder = '{}/{}/{}/{}'.format(self.out_folder, self.topology, self.congestion_control, self.delay_name)

        if not os.path.exists(folder):
            os.makedirs(folder)

        processes = []

        for _, server in iperf_pairs:
            print('server name is {}'.format(server))
            server_cmd = 'python receiver.py -p 5001 '
            server_cmd += '-o {}/{}-{}.txt'.format(folder, 1, server)
            print(server_cmd)

            processes.append(server.popen(shlex.split(server_cmd)))
        time.sleep(1)

        for client, server in iperf_pairs:
            client_cmd = 'python sender.py -p 5001'
            client_cmd += ' -s {}'.format(server.IP())
            client_cmd += ' -o {}/{}-{}.txt'.format(folder, 1, client)
            client_cmd += ' -t {}'.format(20)
            print(client_cmd)
            processes.append(client.popen(shlex.split(client_cmd)))

        for process in processes:
            process.wait()

        print('Done with experiments\n' + '.'*80 + '\n')

    def stop(self):
        self.net.stop()
