import itertools
import os
import shlex
import signal
import time
import subprocess

from MPTopoligies import JsonTopo
from mininet.cli import CLI
from mininet.log import error, info, output
from mininet.net import Mininet
from mininet.util import errFail
from mininet.link import TCLink


def popen_wait(popen_task, timeout=-1):
    delay = 1.0
    while popen_task.poll() is None and timeout > 0:
        time.sleep(delay)
        timeout += delay
    return popen_task.poll() is not None


def system_call(cmd, ignore_codes=None):
    try:
        retcode = subprocess.call(shlex.split(cmd))
        if retcode < 0:
            error('Child was terminated by signal {}\n'.format(-retcode))
        elif retcode > 0 and retcode not in ignore_codes:
            error('Child returned {}\n'.format(retcode))
    except OSError as e:
        error('Execution failed: {}\n'.format(e))


class MPMininet:
    """Create and run multiple paths network"""
    def __init__(self, json_config, congestion_control, delay_name, throughput_name, repetition_number=0,
                 start_cli=False, use_tcpdump=False):
        self.config = json_config
        self.use_tcpdump = use_tcpdump
        self.congestion_control = congestion_control
        self.delay_name, self.tp_name = delay_name, throughput_name
        self.rep_num = repetition_number
        self.topology = json_config['topology_id']
        self.net = None
        self.base_folder = './logs'
        self.out_folder = '{}/{}/{}/{}/{}'.format(self.base_folder, self.topology, self.congestion_control, self.tp_name, self.delay_name)
        self.start(start_cli)

    def start(self, cli):
        self.set_system_variables(mptcp=(self.congestion_control not in ['cubic']), cc=self.congestion_control)

        topo = JsonTopo(self.config)

        # add host=CPULimitedHost if applicable
        self.net = Mininet(topo=topo, link=TCLink)
        topo.setup_routing(self.net)
        self.net.start()

        if cli:
            CLI(self.net)

        # self.run()
        self.run_iperf()

        self.calculate_rtt(del_pcap=False)  # TODO change to actual flag deleting pcap files

        # CLI(self.net)
        self.net.stop()

    @staticmethod
    def _set_system_variable(var, value):
        errFail(['sysctl', '-w', '{0}={1}'.format(var, value)])
        out, err, ret = errFail(['sysctl', '-n', var])
        info('type {} and value "{}"'.format(type(out), out))
        out = out.replace('\n', '')
        if type(value) is bool and bool(out) != value or type(value) is not bool and out != str(value):
            raise Exception("sysctl Fail: setting {} failed, should be {} is {}".format(var, value, out))

    @staticmethod
    def set_system_variables(mptcp, cc):
        # Setting up MPTCP
        MPMininet._set_system_variable('net.mptcp.mptcp_enabled', int(mptcp))

        # Congestion control
        MPMininet._set_system_variable('net.ipv4.tcp_congestion_control', cc)

    def get_iperf_pairings(self):
        pairs = []
        for node in [node for node in self.config['nodes'] if node['id'].startswith('h')]:
            if 'server' in node['properties']:
                pairs.append((str(node['id']), str(node['properties']['server'])))

        # make sure every host is included in some connection
        hosts = itertools.chain.from_iterable(pairs)
        for node in [node for node in self.config['nodes'] if node['id'].startswith('h')]:
            if node['id'] not in hosts:
                error('Host {} not contained in any host pairings!\n'.format(node))

        mininet_host_pairs = map(lambda x: (self.net.get(x[0]), self.net.get(x[1])), pairs)
        return mininet_host_pairs

    def run_iperf(self, runtime=15, skipping=False, time_interval=1):
        """
        Starting iperf on appropriate hosts using the cmp interface provided by minient.

        Note: Mininet also exposes a popen mechanism for executing commands on any node. I encountered issues when using
            it. Somehow the many popen commands lead to iperf3 having a bufferoverflow exception and too many file
            handles beeing open after many build up and tear downs of mininet.

        :param runtime:     how long [seconds] to run iperf
        :param skipping:    should already executed experiments be skipped
        :param time_interval: time step between iperf output lines
        :return: None
        """
        iperf_pairs = self.get_iperf_pairings()

        output('Running iperf_cmd, exp {} repetition: {}\n'.format(self.out_folder, self.rep_num))
        if skipping and os.path.isfile('{}/{}-{}_iperf.txt'.format(self.out_folder, self.rep_num, 'h2')):
            print('already done.')
            return

        if not os.path.exists(self.out_folder):
            os.makedirs(self.out_folder)

        # Start processes on client and server
        for _, server in iperf_pairs:
            server_cmd = ['iperf3', '-s', '-4', '--one-off', '-i', time_interval] # iperf 3: '--one-off', '-J' iperf: '-y', 'C',
            file_name = '{}/{}-{}_iperf.csv'.format(self.out_folder, self.rep_num, server)
            server_cmd += ['&>', file_name]

            server_cmd = map(str, server_cmd)
            info('Running on {}: \'{}\'\n'.format(server, ' '.join(server_cmd)))
            server.sendCmd(server_cmd)
        time.sleep(1)

        for client, server in iperf_pairs:
            if self.use_tcpdump:
                pcap_filter = ' or '.join(['host {}'.format(intf.IP()) for intf in server.intfList()])
                pcap_file = '{}/{}-{}_iperf_dump.pcap'.format(self.out_folder, self.rep_num, client)
                dump_cmd = ['tcpdump', '-i', 'any', '-w', pcap_file]
                dump_cmd += shlex.split(pcap_filter)
                dump_cmd += ['&>', '/dev/null', '&']

                dump_cmd = map(str, dump_cmd)
                info('Running on {}: \'{}\'\n'.format(client, ' '.join(dump_cmd)))
                client.cmd(dump_cmd)

            client_cmd = ['iperf3', '-c', server.IP(), '-t', runtime, '-i', time_interval, '-4'] # '-J' iperf: '-y', 'C',
            file_name = '{}/{}-{}_iperf.csv'.format(self.out_folder, self.rep_num, client)
            client_cmd += ['&>', file_name, ';', 'echo', '$?']

            client_cmd = map(str, client_cmd)
            info('Running on {}: \'{}\'\n'.format(client, ' '.join(client_cmd)))

            client.sendCmd(client_cmd)

        # Wait for completion and stop all processes
        for client, _ in iperf_pairs:
            o = client.waitOutput()
            # make sure o[-3:-2] is exit code 0!
            if o[-3:-2] not in ['0']:
                error('client popen did not exit correctly\n')
                raise RuntimeError('Client iperf did not exit correctly, error code {}\n'.format(o[-3:-2]),
                                   self.out_folder, self.rep_num)

            # interrupt tcpdump
            client.cmd('pkill -SIGINT tcpdump')
        for _, server in iperf_pairs:
            server.sendInt()

        time.sleep(1)
        output('\t\tDone with experiment, cleanup\n')
        system_call('pkill iperf3', ignore_codes=[1])
        system_call('pkill tcpdump', ignore_codes=[1])

    def calculate_rtt(self, del_pcap):
        """
        Use tshark to extract RTT times from the pcap file generated by tcpdump.

        :param del_pcap: delete tcpdump file after calculations
        :return: None
        """
        if not self.use_tcpdump:
            info('No dumps to analyze continue.\n')
            return

        for client, _ in self.get_iperf_pairings():
            pcap_file = '{}/{}-{}_iperf_dump.pcap'.format(self.out_folder, self.rep_num, client)
            out_file = '{}/{}-{}_iperf_dump.csv'.format(self.out_folder, self.rep_num, client)
            parse_cmd = ['tshark', '-r', pcap_file]
            parse_cmd += ['-e', 'frame.time_relative', '-e', 'tcp.stream', '-e', 'ip.src', '-e', 'ip.dst',
                          '-e', 'tcp.analysis.ack_rtt', '-e', 'tcp.options.mptcp.datalvllen', '-T', 'fields',
                          '-E', 'header=y']
            with open(out_file, 'w+') as f:
                p = subprocess.Popen(parse_cmd, stdout=f, stderr=subprocess.PIPE)
                _, err = p.communicate()
                p.terminate()

            if del_pcap:
                os.remove(pcap_file)

    def run(self, runtime=30):
        iperf_pairs = self.get_iperf_pairings()
        info("Running clients and servers, repetition: {}\n".format(self.rep_num))

        folder = '{}/{}/{}/{}/{}'.format(self.out_folder, self.topology, self.congestion_control, self.tp_name, self.delay_name)

        if not os.path.exists(folder):
            os.makedirs(folder)

        processes = []

        for _, server in iperf_pairs:
            server_cmd = 'python receiver.py -p 5001 '
            server_cmd += '-o {}/{}-{}.txt'.format(folder, self.rep_num, server)
            # server_cmd += ' --size {}'.format(8000)
            print('Running \'{}\' on {}'.format(server_cmd, server))

            processes.append(server.popen(shlex.split(server_cmd)))
        time.sleep(1)

        for client, server in iperf_pairs:
            client_cmd = 'python sender.py -p 5001'
            client_cmd += ' -s {}'.format(server.IP())
            client_cmd += ' -o {}/{}-{}.txt'.format(folder, self.rep_num, client)
            client_cmd += ' -t {}'.format(runtime)
            # client_cmd += ' --size {}'.format(8000)
            print('Running \'{}\' on {}'.format(client_cmd, client))
            processes.append(client.popen(shlex.split(client_cmd)))

        for process in processes:
            process.wait()

        print('Done with experiment\n' + '.'*80 + '\n')

    def stop(self):
        self.net.stop()
