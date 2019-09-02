import itertools
import os
import shlex
import signal
import time
import subprocess
import numpy as np

from MPTopoligies import JsonTopo
from mininet.cli import CLI
from mininet.log import error, info, debug, output
from mininet.net import Mininet
from mininet.util import errFail
from mininet.link import TCLink

from utils import get_group_with_value, MPTCP_CCS, system_call


class MPMininet:
    """Create and run multiple paths network"""
    def __init__(self, json_config, repetition_number, start_cli=False, use_tcpdump=True, keep_tcpdumps=True):
        self.config = json_config
        self.use_tcpdump, self.keep_dumps = use_tcpdump, keep_tcpdumps
        self.rep_num = repetition_number
        self.topology = json_config['topology_id']
        self.net = None
        self.base_folder = './logs'
        delay_dir = '_'.join(['{}ms'.format(float(delay)) for _, delay in get_group_with_value(self.config, 'latency')])
        bw_dir = '_'.join(['{}Mbps'.format(int(rate)) for _, rate in get_group_with_value(self.config, 'bandwidth')])
        self.ccs = [cc for _, _, cc in self.get_iperf_config_pairings()]
        cc_dir = '_'.join(self.ccs)
        self.out_folder = '{}/{}/{}/{}/{}'.format(self.base_folder, self.topology, cc_dir, bw_dir, delay_dir)
        self.start(start_cli)

    def start(self, cli, skipping=True):
        output('Running throughput experiment, exp {} repetition: {}\n'.format(self.out_folder, self.rep_num))

        if not os.path.exists(self.out_folder):
            os.makedirs(self.out_folder)

        if skipping and os.path.isfile('{}/{}-{}_iperf_dump.csv'.format(self.out_folder, self.rep_num, 'h1')):
            output('\talready done.\n')
            return

        # Check if mptcp configuration is possible and set system variables
        is_mptcp = [cc in MPTCP_CCS for cc in self.ccs]
        if any(is_mptcp) and not all(is_mptcp):
            raise NotImplementedError('Running a non mptcp and a mptcp congestion control algorithm simultaneously is '
                                      'not supported. {}\n'.format(self.ccs))
        self.set_sysctl_variable('net.mptcp.mptcp_enabled', int(any(is_mptcp)))

        topo = JsonTopo(self.config)
        # add host=CPULimitedHost if applicable
        self.net = Mininet(topo=topo, link=TCLink)
        topo.setup_routing(self.net)
        self.net.start()

        if cli:
            CLI(self.net)
        else:
            # self.run()
            self.run_iperf()

            self.calculate_rtt(keep_pcap=self.keep_dumps)

        self.net.stop()

    @staticmethod
    def _get_available_congestioncontrol_algos():
        out, err, ret = errFail(['sysctl', '-n', 'net.ipv4.tcp_available_congestion_control'])
        return out.strip().split()

    @staticmethod
    def set_sysctl_variable(var, value):
        """
        Use Mininet command execution to set and verify sysctl variables.

        :param var:     sysctl var name, e.g. 'net.mptcp.mptcp_enabled'
        :param value:   variable value, e.g. '1'
        :return:
        """
        errFail(['sysctl', '-w', '{0}={1}'.format(var, value)])
        out, err, ret = errFail(['sysctl', '-n', var])
        debug('type {} and value "{}"\n'.format(type(out), out.strip()))
        out = out.replace('\n', '')
        if type(value) is bool and bool(out) != value or type(value) is not bool and out != str(value):
            raise Exception("sysctl Fail: setting {} failed, should be {} is {}".format(var, value, out))

    def get_iperf_pairings(self):
        """
        Turn name into mininet host references.
        :return:    list of tuples (client, server, cc)
        """
        pairings = self.get_iperf_config_pairings()
        return list(map(lambda (s, d, c): (self.net.get(s), self.net.get(d), c), pairings))

    def get_iperf_config_pairings(self):
        """
        Read pairings from JSON config, which clients talks to which server with what congestion control algorithm.
        :return:    list of tuples (client_name, server_name, cc)
        """
        pairs = []  # contains tuples (client, server, congestion control algorithm)
        ccs = []
        for node in [node for node in self.config['nodes'] if node['id'].startswith('h')]:
            if 'server' in node['properties']:
                assert('cc' in node['properties'])
                pairs.append((str(node['id']),
                              str(node['properties']['server'])))
                ccs.append(str(node['properties']['cc']))

        # sort the lists alphabetically (sort by client/server pairs)
        mixed = sorted(zip(pairs, ccs))
        ccs = [cc for _, cc in mixed]
        pairs = [pair for pair, _ in mixed]

        # make sure every host is included in some connection
        hosts = itertools.chain.from_iterable(pairs)
        for node in [node for node in self.config['nodes'] if node['id'].startswith('h')]:
            if node['id'] not in hosts:
                error('Host {} not contained in any host pairings!\n'.format(node))
        if any(cc not in self._get_available_congestioncontrol_algos() for cc in ccs):
            error('Congestion Control algorithm not allowed! Tried to use {}.\n'.format(', '.join(ccs)))
            exit(2)

        assert(len(pairs) == len(ccs))
        return [hs + (cc,) for hs, cc in zip(pairs, ccs)]

    def get_iperf3_cmds(self, client, server, runtime, time_interval, cc):
        """
        Generate iperf3 commands to run on client/server pair.
        :param client:          mininet client reference
        :param server:          mininet server reference
        :param runtime:         time to run in seconds
        :param time_interval:   report interval for iperf3
        :param cc:              congestion control algorithm name to use
        :return:                tuple (cli_cmd, srv_cmd)
        """
        file_name = '{}/{}_'.format(self.out_folder, self.rep_num)
        file_name += '{}_iperf.csv'

        client_cmd = ['iperf3', '-c', server.IP(), '-t', runtime, '-i', time_interval, '-f', 'm', '-4', '-C', cc]
        client_cmd += ['&>', file_name.format(client)]

        server_cmd = ['iperf3', '-s', '-4', '--one-off', '-f', 'm', '-i', time_interval]
        server_cmd += ['&>', file_name.format(server)]

        return map(str, client_cmd), map(str, server_cmd)

    def run_iperf(self, runtime=120, time_interval=0.1):
        """
        Starting iperf on appropriate hosts using the cmp interface provided by minient.

        Note: Mininet also exposes a popen mechanism for executing commands on any node. I encountered issues when using
            it. Somehow the many popen commands lead to iperf3 having a bufferoverflow exception.
            https://github.com/esnet/iperf/issues/448

        :param runtime:     how long [seconds] to run iperf
        :param time_interval: time step between iperf output lines
        :return: None
        """
        iperf_pairs = self.get_iperf_pairings()

        # Generate iperf commands for both server and client
        iperf_cmds = {}  # map host to iperf cmd
        for cli, srv, cc in iperf_pairs:
            cli_cmd, srv_cmd = self.get_iperf3_cmds(cli, srv, runtime, time_interval, cc)
            iperf_cmds[cli] = cli_cmd
            iperf_cmds[srv] = srv_cmd

        # Start processes on client and server
        for _, server, _ in iperf_pairs:
            info('Running on {}: \'{}\'\n'.format(server, ' '.join(iperf_cmds[server])))
            server.sendCmd(iperf_cmds[server])
        time.sleep(1)

        for client, server, cc in iperf_pairs:
            if self.use_tcpdump:
                pcap_filter = ' or '.join(['host {}'.format(intf.IP()) for intf in server.intfList()])
                pcap_file = '{}/{}-{}_iperf_dump.pcap'.format(self.out_folder, self.rep_num, client)
                dump_cmd = ['tcpdump', '-i', 'any', '-w', pcap_file]
                dump_cmd += shlex.split(pcap_filter)
                dump_cmd += ['&>', '/dev/null', '&']  # Note: trailing `&` lets the command run in the background
                dump_cmd = map(str, dump_cmd)

                info('Running on {}: \'{}\'\n'.format(client, ' '.join(dump_cmd)))
                client.cmd(dump_cmd)

            # Note: check the exit code of iperf with `$?`
            cli_cmd = iperf_cmds[client] + [';', 'echo', '$?']
            info('Running on {}: \'{}\'\n'.format(client, ' '.join(cli_cmd)))
            client.sendCmd(cli_cmd)

        # Wait for completion and stop all processes
        for client, _, _ in iperf_pairs:
            o = client.waitOutput()
            # make sure exit code 0!
            if not o.strip().endswith('0'):
                error('client cmd did not exit correctly\n')
                raise RuntimeError('Client iperf did not exit correctly, error code {}\n'.format(o.strip()),
                                   self.out_folder, self.rep_num)

            # interrupt tcpdump
            client.cmd('pkill -SIGINT tcpdump')

        # Send interrupt to iperf3 servers and wait for completion, without waiting mininet will fail on assertion
        for _, server, _ in iperf_pairs:
            server.sendInt()
            _ = server.monitor(timeoutms=100)

        time.sleep(1)
        output('\t\tDone with experiment, cleanup\n')
        system_call('pkill iperf3', ignore_codes=[1])
        system_call('pkill tcpdump', ignore_codes=[1])

    def calculate_rtt(self, keep_pcap):
        """
        Use tshark to extract RTT times from the pcap file generated by tcpdump.

        :param keep_pcap: keep tcpdump file after calculations
        :return: None
        """
        if not self.use_tcpdump:
            info('No dumps to analyze continue.\n')
            return

        for client, _, _ in self.get_iperf_pairings():
            pcap_file = '{}/{}-{}_iperf_dump.pcap'.format(self.out_folder, self.rep_num, client)
            out_file = '{}/{}-{}_iperf_dump.csv'.format(self.out_folder, self.rep_num, client)
            parse_cmd = ['tshark', '-r', pcap_file]
            parse_cmd += ['-e', 'frame.time_relative', '-e', 'tcp.stream', '-e', 'ip.src', '-e', 'ip.dst',
                          '-e', 'tcp.analysis.ack_rtt', '-e', 'tcp.options.mptcp.datalvllen', '-T', 'fields',
                          '-E', 'header=y']
            with open(out_file, 'w+') as f:
                p = subprocess.Popen(parse_cmd, stdout=f, stderr=subprocess.PIPE)
                _, err = p.communicate()

            if not keep_pcap:
                os.remove(pcap_file)

    def run(self, runtime=30):
        iperf_pairs = self.get_iperf_pairings()
        info("Running clients and servers, repetition: {}\n".format(self.rep_num))

        processes = []

        for _, server, _ in iperf_pairs:
            server_cmd = 'python receiver.py -p 5001 '
            server_cmd += '-o {}/{}-{}.txt'.format(self.out_folder, self.rep_num, server)
            # server_cmd += ' --size {}'.format(8000)
            print('Running \'{}\' on {}'.format(server_cmd, server))

            processes.append(server.popen(shlex.split(server_cmd)))
        time.sleep(1)

        for client, server, _ in iperf_pairs:
            client_cmd = 'python sender.py -p 5001'
            client_cmd += ' -s {}'.format(server.IP())
            client_cmd += ' -o {}/{}-{}.txt'.format(self.out_folder, self.rep_num, client)
            client_cmd += ' -t {}'.format(runtime)
            # client_cmd += ' --size {}'.format(8000)
            print('Running \'{}\' on {}'.format(client_cmd, client))
            processes.append(client.popen(shlex.split(client_cmd)))

        for process in processes:
            process.wait()

        print('Done with experiment\n' + '.'*80 + '\n')

    def stop(self):
        self.net.stop()
