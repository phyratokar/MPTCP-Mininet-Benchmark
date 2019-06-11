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

parser = ArgumentParser(description="MPTCP TP and Latency tests")

parser.add_argument('--cc',
                    help="Congestion Control Algorithm used (lia, olia, balia, wVegas)",
                    choices=['lia', 'olia', 'balia', 'wvegas'],
                    default='balia')

parser.add_argument('--topo',
                    help="Topology to use",
                    choices=['shared_link', 'two_paths', '', ''],
                    default='MPflow')

parser.add_argument('--asymmetry',
                    '-a',
                    help="How big should the latency differ between paths [1.0-3.0]",
                    type=float,
                    default=1.0)
args = parser.parse_args()


def simpleMptcp(net):
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


def twoSendersMptcp(net):
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


def main():
    """Create and run multiple link network"""
    net = MPMininet()
    net.start(topology_name=args.topo, congestion_control=args.cc)

    # Debug CLI
    CLI(net.get_net())

    # Now we run the client and server
    # simpleMptcp(net)
    # twoSendersMptcp(net.get_net())
    net.run()

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
