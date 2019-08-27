import copy
import os
import pprint
import itertools
from argparse import ArgumentParser

import numpy as np

from mininet.cli import CLI
from mininet.net import Mininet
from mininet.link import TCLink
from mininet.log import setLogLevel, info, error, debug

from MPMininet import MPMininet
from MPTopoligies import JsonTopo
from utils import read_json, extract_groups, check_system

Topologies_file = 'topologies/{}.json'
Congestion_control_algorithms = ['lia', 'olia', 'balia', 'wvegas', 'cubic']


def adjust_group_config(config, group_name, group, value):
    """
    Change latency or bandwidth value of entire group in JSON config.

    :param config:      JSON/dict config to be changed (inplace!)
    :param group_name:  'latency_group' / 'bandwidth_group'
    :param group:       groupname, e.g. 'a' or 'b'
    :param value:       value to set, e.g. '10.0'
    :return:            number of link properties changed
    """
    value_name = group_name.partition('_')[0]
    changes = 0
    for link in config['links']:
        if group_name in link['properties']:
            if link['properties'][group_name] == group:
                link['properties'][value_name] = value
                changes += 1
    return changes


def adjust_cc_config(config, cc):
    for host in (n for n in config['nodes'] if n['id'].startswith('h')):
        if 'cc' in host['properties']:
            host['cc'] = cc


def run_latency(topo_name):
    group_name = 'latency_group'
    delays = np.arange(0, 102, 10)

    # Read in config file containing the topology
    orig_config = read_json(Topologies_file.format(topo_name))
    latency_groups, n_changeable_links = extract_groups(orig_config, group_field=group_name)
    assert(len(latency_groups) <= 2)  # making sure we only deal with 2 or less groups!

    delays_b = delays if len(latency_groups) > 1 else delays[:1]

    for rep in range(3):
        for cc_name in Congestion_control_algorithms:
            for delay_a in delays:
                for delay_b in delays_b:

                    # generate changed config
                    config = copy.deepcopy(orig_config)
                    adjust_cc_config(config, cc_name)

                    changed = 0
                    for group, val in zip(latency_groups, [delay_a, delay_b]):
                        # print('changing group {} to value {}'.format(group, val))
                        changed += adjust_group_config(config, group_name, group, val)

                    if changed != n_changeable_links: # TODO move this check out of the experiment loop, should be enought to run once!
                        raise RuntimeError('There are more links with the "{}" property than just changed in the config!'.format(group_name))

                    # pprint.pprint(cur_config)
                    # Run experiments
                    MPMininet(config, repetition_number=rep)
                    # return


def run_sym_configs(topo_name, group_name, group_values):
    """
    Exhaustively explores the configuration space for a group with the given values.
    :param topo_name:   topology name (topo file in ./topologies/_name_.json)
    :param group_name:  name of link group to change ('latency_group' / 'bandwidth_group')
    :param group_values: configuration values to explore
    :return:
    """
    # Read in config file containing the topology
    orig_config = read_json(Topologies_file.format(topo_name))
    groups, n_changeable_links = extract_groups(orig_config, group_field=group_name)
    bw_groups, _ = extract_groups(orig_config, group_field='bandwidth_group')
    de_groups, _ = extract_groups(orig_config, group_field='latency_group')

    # generate all configurations to run for the current group, i.e. for 2 groups a list with tuples [(v_a, v_b)]
    mgroups = tuple([group_values] * len(groups))
    values_product = list(itertools.product(*mgroups))

    for rep in range(3):
        for cc_name in Congestion_control_algorithms:
            for cur_values in values_product:
                # generate changed config
                config = copy.deepcopy(orig_config)
                adjust_cc_config(config, cc_name)

                changed = 0
                for group, val in zip(groups, cur_values):
                    info('Changing group {} to value {}\n'.format(group, val))
                    changed += adjust_group_config(config, group_name, group, val)

                if changed != n_changeable_links:  # TODO move this check out of the experiment loop, should be enought to run once!
                    raise RuntimeError('There are more links with the "{}" property than just changed in the config!'.format(group_name))

                # pprint.pprint(config)

                # Run experiment and shut it down immediately afterwards
                MPMininet(config, repetition_number=rep, start_cli=args.cli,
                          use_tcpdump=(not args.no_dtcp), keep_tcpdumps=args.dtcp)
                # return


def run_tp_fairness(topo_name):
    group_name = 'bandwidth_group'
    bws = [5, 9, 13, 15, 17, 21, 25]

    # Read in config file containing the topology
    orig_config = read_json(Topologies_file.format(topo_name))
    tp_groups, num_changeable_links = extract_groups(orig_config, group_field='bandwidth_group')

    print('we have {} tp groups'.format(len(tp_groups)))

    tps_a = [5, 9, 13, 15, 17, 21, 25]
    tps_b = [5, 9, 13, 15, 17, 21, 25]

    for rep in range(3):
        for cc_name in Congestion_control_algorithms:
            for tp_a in tps_a:
                for tp_b in tps_b:
                    config = copy.deepcopy(orig_config)
                    adjust_cc_config(config, cc_name)

                    # Set link bandwidths
                    for link in config['links']:
                        if 'bandwidth_group' in link['properties']:
                            if link['properties']['bandwidth_group'] == 'a':
                                link['properties']['bandwidth'] = tp_a
                            elif link['properties']['bandwidth_group'] == 'b':
                                link['properties']['bandwidth'] = tp_b
                            else:
                                raise NotImplementedError('Not yet implemented more than two bandwidth_groups for links. {}'.format(link))
                        else:
                            # TODO handle error case
                            pass

                    # Run experiments
                    MPMininet(config, repetition_number=rep)
                    # return


def main():
    """Create and run multiple link network"""
    check_system()

    # run_latency('two_paths')
    # run_tp_fairness('mp-vs-sp')
    # run_tp_fairness_single('single_path')

    if args.run:
        if args.topo == 'mp_vs_sp':
            # Only test change in bw
            bandwidths = [5, 10, 15, 20, 25]
            latencies = []
        elif args.topo == 'single_bottleneck' or args.topo == 'asym_mp':
            bandwidths = []
            latencies = [10]
        else:
            latencies = np.arange(0, 102, 30)
            bandwidths = [5, 10, 15, 20, 25]

        if args.run == 'de':
            # run_latency(args.topo)
            run_sym_configs(args.topo, group_name='latency_group', group_values=latencies)
        elif args.run == 'tp':
            # run_tp_fairness(args.topo)
            run_sym_configs(args.topo, group_name='bandwidth_group', group_values=bandwidths)
        elif args.run == 'all':
            run_sym_configs(args.topo, group_name='bandwidth_group', group_values=bandwidths)
            run_sym_configs(args.topo, group_name='latency_group', group_values=latencies)
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

    parser.add_argument('--dtcp', '-d',
                        action='store_true',
                        help="Store captured tcpdumps per connections")

    parser.add_argument('--no_dtcp',
                        action='store_true',
                        help="Do NOT use tcpdump (no RTT analysis possible)")

    parser.add_argument('--cli',
                        action='store_true',
                        help="Instead of running experiments, open CLI")

    parser.add_argument('--run',
                        choices=['de', 'tp', 'all'],
                        help="Which tasks to run")

    parser.add_argument('--log',
                        choices=['info', 'debug', 'output', 'warning', 'error', 'critical'],
                        help="Mininet logging level")

    parser.add_argument('--topo',
                        help="Topology to use",
                        choices=['asym_mp', 'mp_vs_sp', 'shared_link', 'single_bottleneck', 'single_path', 'two_paths'],
                        required=True,
                        default='two_paths')

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
        os.system("killall -9 top bwm-ng tcpdump cat mnexec iperf iperf3; mn -c")
