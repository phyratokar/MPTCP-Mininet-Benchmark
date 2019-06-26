import copy
import json
import os
import shlex
from argparse import ArgumentParser

import numpy as np

from MPMininet import MPMininet
from MPTopolies import JsonTopo
from mininet.cli import CLI
from mininet.link import TCLink
from mininet.net import Mininet
from mininet.log import setLogLevel

Congestion_control_algorithms = ['lia', 'olia', 'balia', 'wvegas', 'cubic']


def read_json(file_name):
    if not os.path.isfile(file_name):
        print('JSON topology file not found! {}'.format(file_name))
        exit(1)

    with open(file_name, 'r') as f:
        config = json.load(f)

    return config


def run_latency(topo_name):
    delays = np.arange(0, 102, 20)

    for rep in range(3):  # [2:]: # fixme: remove less runs and less cc
        for cc_name in Congestion_control_algorithms:  # [1:]:
            for delay_a in delays:
                for delay_b in delays:  # [d for d in delays if d >= delay_a]:

                    # Read in config file containing the topology
                    config = read_json('topologies/{}.json'.format(topo_name))

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
                    tp_dir = '{}Mbps-{}Mbps'.format(10, 10)

                    # Run experiments
                    MPMininet(config, cc_name, delay_name=delay_dir, throughput_name=tp_dir, repetition_number=rep)
                    # return


def extract_groups(config, kind='lt'):
    if kind is 'lt':
        group_field = 'latency_group'
    elif kind is 'tp':
        group_field = 'throughput_group'
    else:
        raise NotImplementedError('Only latency and throughput groups currently supported, {} not recognized.'.format(kind))
    groups = set()
    for link in config['links']:
        if 'latency_group' in link['properties']:
            groups.add(link['properties'][group_field])
    return groups


def run_tp_fairness(topo_name):
    # Read in config file containing the topology
    orig_config = read_json('topologies/{}.json'.format(topo_name))
    tp_groups = extract_groups(orig_config, kind='tp')

    # tps_a = [5, 7, 9, 11, 12, 13, 14, 15, 16, 17, 18, 19, 21, 23, 25]
    # tps_b = [5, 7, 9, 11, 12, 13, 14, 15, 16, 17, 18, 19, 21, 23, 25]

    tps_a = [5, 9, 13, 15, 17, 21, 25]
    tps_b = [5, 9, 13, 15, 17, 21, 25]

    for rep in range(3):
        for cc_name in Congestion_control_algorithms:
            for tp_a in tps_a:
                for tp_b in tps_b:
                    config = copy.deepcopy(orig_config)

                    # Set link throughputs
                    for link in config['links']:
                        if 'throughput_group' in link['properties']:
                            if link['properties']['throughput_group'] == 'a':
                                link['properties']['throughput'] = tp_a
                            elif link['properties']['throughput_group'] == 'b':
                                link['properties']['throughput'] = tp_b
                            else:
                                raise NotImplementedError('Not yet implemented more than two throughput_groups for links. {}'.format(link))
                        else:
                            raise

                    delay_dir = '{}ms-{}ms'.format(10, 10)
                    tp_dir = '{}Mbps-{}Mbps'.format(tp_a, tp_b)

                    # Run experiments
                    MPMininet(config, cc_name, delay_name=delay_dir, throughput_name=tp_dir, repetition_number=rep)
                    return


def run_tp_fairness_single(topo_name):
    # Read in config file containing the topology
    orig_config = read_json('topologies/{}.json'.format(topo_name))
    tp_groups = extract_groups(orig_config, kind='tp')

    # tps_a = [5, 7, 9, 11, 12, 13, 14, 15, 16, 17, 18, 19, 21, 23, 25]
    tps_a = [5, 9, 13, 15, 17, 21, 25]

    for rep in range(3):
        for cc_name in Congestion_control_algorithms:
            for tp_a in tps_a:
                config = copy.deepcopy(orig_config)

                # Set link throughputs
                for link in config['links']:
                    if 'throughput_group' in link['properties']:
                        if link['properties']['throughput_group'] == 'a':
                            link['properties']['throughput'] = tp_a
                        else:
                            raise NotImplementedError('Not yet implemented more than two throughput_groups for links. {}'.format(link))

                delay_dir = '{}ms-{}ms'.format(10, 10)
                tp_dir = '{}Mbps-{}Mbps'.format(tp_a, 0)

                # Run experiments

                MPMininet(config, cc_name, delay_name=delay_dir, throughput_name=tp_dir, repetition_number=rep)


def main():
    """Create and run multiple link network"""
    if args.all:
        run_latency('two_paths')
        # run_tp_fairness('mp-vs-sp')
        # run_tp_fairness_single('single_path')
        pass
    else:
        config = read_json('topologies/' + args.topo + '.json')
        topo = JsonTopo(config)
        # topo = SingleMPFlowTopo()

        # add host=CPULimitedHost if applicable
        net = Mininet(topo=topo, link=TCLink)
        topo.setup_routing(net)
        net.start()

        CLI(net)

        net.stop()


if __name__ == '__main__':
    parser = ArgumentParser(description="MPTCP TP and Latency tests")

    parser.add_argument('--all', '-a',
                        action='store_true',
                        help="Run all available tests")

    parser.add_argument('--log',
                        choices=['info', 'debug', 'output', 'warning', 'error', 'critical'],
                        help="Mininet logging level")

    parser.add_argument('--cc',
                        help="Congestion Control Algorithm used (lia, olia, balia, wVegas)",
                        choices=Congestion_control_algorithms,
                        default=Congestion_control_algorithms[1])

    parser.add_argument('--topo',
                        help="Topology to use",
                        choices=['shared_link', 'two_paths', 'mp-vs-sp', 'single_path'],
                        default='two_paths')

    parser.add_argument('--asymmetry',
                        help="How big should the latency differ between paths [1.0-3.0]",
                        type=float,
                        default=1.0)
    args = parser.parse_args()

    try:
        if args.log:
            setLogLevel(args.log)
        main()
    except:
        print("-" * 80)
        print("Caught exception.  Cleaning up...")
        print("-"*80)
        import traceback
        traceback.print_exc()
        os.system("killall -9 top bwm-ng tcpdump cat mnexec iperf; mn -c")
