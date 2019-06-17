import json

from MPMininet import MPMininet
from mininet.topo import Topo
from mininet.net import Mininet
from mininet.cli import CLI
from mininet.node import CPULimitedHost
from mininet.link import TCLink
from mininet.util import dumpNodeConnections
from mininet.log import setLogLevel
import shlex

from subprocess import Popen, PIPE
import os
from argparse import ArgumentParser

from MPTopolies import SingleMPFlowTopo, SharedLinkTopo, MPagainstSPTopo, MPTopo, JsonTopo

Congestion_control_algorithms = ['lia', 'olia', 'balia', 'wvegas']

parser = ArgumentParser(description="MPTCP TP and Latency tests")

parser.add_argument('--all', '-a',
                    action='store_true',
                    help="Run all available tests")

parser.add_argument('--cc',
                    help="Congestion Control Algorithm used (lia, olia, balia, wVegas)",
                    choices=Congestion_control_algorithms,
                    default=Congestion_control_algorithms[1])

parser.add_argument('--topo',
                    help="Topology to use",
                    choices=['shared_link', 'two_paths', '', ''],
                    default='two_paths')

parser.add_argument('--asymmetry',
                    help="How big should the latency differ between paths [1.0-3.0]",
                    type=float,
                    default=1.0)
args = parser.parse_args()


def read_json(file_name):
    if not os.path.isfile(file_name):
        print('JSON topology file not found! {}'.format(file_name))
        exit(1)

    with open(file_name, 'r') as f:
        config = json.load(f)

    return config


def simple_mptcp(net):
    h1, h2 = net.get('h1', 'h2')
    print("Running client and server")

    server_command = 'python receiver.py -p 5001 -o {}-{}-rcv{}.txt'.format(args.cc, args.topo, 2)
    server_args = shlex.split(server_command)
    server = h2.popen(server_args)
    client_command = 'python sender.py -s 10.0.0.2 -p 5001 -o {}-{}-snd{}.txt -t {}'.format(args.cc, args.topo, 1, 30)
    client_args = shlex.split(client_command)
    client = h1.popen(client_args)
    client.wait()
    server.wait()

    print('Done with experiments.\n' + '-'*80 + '\n')


def two_senders_mptcp(net):
    h1, h2, h3, h4 = net.get('h1', 'h2', 'h3', 'h4')
    print("Running clients and servers")

    server_command = "python receiver.py -p 5001 -o {}-{}".format(args.cc, args.topo) + '-rcv{}.txt'
    server2 = h2.popen(shlex.split(server_command.format(2)))
    server4 = h4.popen(shlex.split(server_command.format(4)))

    client_command = 'python sender.py -s 10.0.0.2 -p 5001 -o {}-{}'.format(args.cc, args.topo) + '-snd{}.txt -t {}'
    client1 = h1.popen(shlex.split(client_command.format(1, 30)))
    client_command = 'python sender.py -s 10.0.0.4 -p 5001 -o {}-{}'.format(args.cc, args.topo) + '-snd{}.txt -t {}'
    client3 = h3.popen(shlex.split(client_command.format(3, 30)))
    client1.wait()
    client3.wait()
    server2.wait()
    server4.wait()

    print("Done with experiments.\n" + "-"*80 + "\n")


def run_config():
    topo_name = args.topo
    cc_name = args.cc
    config = read_json('topologies/' + topo_name + '.json')
    variable_links = [(position, link) for position, link in enumerate(config['links'])
                      if 'latency_tests' in link['properties']]

    for link_delay in variable_links[0][1]['properties']['latency_tests']:
        config['links'][variable_links[0][0]]['properties']['latency'] = link_delay

        # TODO add second changing delay if applicable
        net = MPMininet(config, cc_name, link_delay, start_cli=True)
        #
        CLI(net.get_net())
        #
        net.run()

        net.get_net().stop()


def run_all():
    topo_name = args.topo
    config = read_json('topologies/{}.json'.format(topo_name))
    variable_links = [(position, link) for position, link in enumerate(config['links'])
                      if 'latency_tests' in link['properties']]

    for cc_name in Congestion_control_algorithms:
        for (delay_a, delay_b) in [(5, 5), (1, 1), (1, 2), (1, 3), (1, 5), (2, 2), (2, 3), (2, 5), (3, 3), (3, 5)]:

            # Set link latency
            for link in config['links']:
                if 'latency_group' in link['properties']:
                    if link['properties']['latency_group'] == 'a':
                        link['properties']['latency'] = delay_a
                    elif link['properties']['latency_group'] == 'b':
                        link['properties']['latency'] = delay_b
                    else:
                        raise NotImplementedError('Not yet implemented more than two latency_groups for links. {}'.format(link))

            delay_dir = '{}ms-{}ms'.format(delay_a, delay_b)

            net = MPMininet(config, cc_name, delay_name=delay_dir)

            net.run()
            net.stop()


def main():
    """Create and run multiple link network"""
    if args.all:
        run_all()
    else:
        config = read_json('topologies/' + args.topo + '.json')
        topo = JsonTopo(config)
        # topo = SingleMPFlowTopo()

        # add host=CPULimitedHost if applicable
        net = Mininet(topo=topo, link=TCLink)
        topo.setup_routing(net)
        net.start()

        CLI(net)



        # CLI(net)
        net.stop()


if __name__ == '__main__':
    try:
        main()
    except:
        print("-" * 80)
        print("Caught exception.  Cleaning up...")
        print("-"*80)
        import traceback
        traceback.print_exc()
        os.system("killall -9 top bwm-ng tcpdump cat mnexec iperf; mn -c")
