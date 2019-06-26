import itertools
import os
import shlex
import signal
import time

from MPTopolies import JsonTopo
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


class MPMininet:
    """Create and run multiple paths network"""
    def __init__(self, json_config, congestion_control, delay_name, throughput_name, repetition_number=0, start_cli=False):
        self.config = json_config
        self.congestion_control = congestion_control
        self.delay_name, self.tp_name = delay_name, throughput_name
        self.rep_num = repetition_number
        self.topology = json_config['topology_id']
        self.net = None
        self.out_folder = './logs'
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

    def run_iperf(self, runtime=10, skipping=False, capture_tcp=True):
        iperf_pairs = self.get_iperf_pairings()
        folder = '{}/{}/{}/{}/{}'.format(self.out_folder, self.topology, self.congestion_control, self.tp_name, self.delay_name)

        output('Running iperf3, repetition: {}\n'.format(self.rep_num))
        if skipping and os.path.isfile('{}/{}-{}_iperf.txt'.format(folder, self.rep_num, 'h2')):
            print('already done.')
            return

        if not os.path.exists(folder):
            os.makedirs(folder)

        # TODO: start tcpdump per sending client
        # TODO: start iperf client per client and wait for completion of them all, throw error if any of them is not
        # connected or encounters issue

        servers = []
        clients = []
        client_tcpdumps = []

        # Start processes on client and server
        for _, server in iperf_pairs:
            server_cmd = ['iperf3', '-s', '-J', '-i', 0.1]
            file_name = '{}/{}-{}_iperf.txt'.format(folder, self.rep_num, server)

            server_cmd = map(str, server_cmd)
            info('Running on {}: \'{}\'\n'.format(server, ' '.join(server_cmd)))
            with open(file_name, 'w') as f:
                servers.append(server.popen(server_cmd, stdout=f, stderr=f))
        time.sleep(1)

        for client, server in iperf_pairs:
            if capture_tcp:
                pcap_filter = ' or '.join(['host {}'.format(intf.IP()) for intf in server.intfList()])
                pcap_file = '{}/{}-{}_iperf_dump.txt'.format(folder, self.rep_num, client)
                dump_cmd = ['tcpdump', '-i', 'any', '-w', pcap_file]
                dump_cmd += shlex.split(pcap_filter)

                dump_cmd = map(str, dump_cmd)
                info('Running on {}: \'{}\'\n'.format(client, ' '.join(dump_cmd)))
                client_tcpdumps.append(client.popen(dump_cmd))

            client_cmd = ['iperf3', '-J', '-c', server.IP(), '-t', runtime, '-i', 0.1]
            # client_cmd += ' --size {}'.format(8000)

            client_cmd = map(str, client_cmd)
            info('Running on {}: \'{}\'\n'.format(client, ' '.join(client_cmd)))

            file_name = '{}/{}-{}_iperf.txt'.format(folder, self.rep_num, client)
            with open(file_name, 'w') as f:
                clients.append(client.popen(client_cmd, stdout=f, stderr=f))

        # Wait for completion and stop all processes
        for process in clients:
            if popen_wait(process, timeout=runtime + 5) is None:
                error('client popen did not exit correctly\n')
                process.kill()

        for process in servers:
            # os.system('killall -SIGINT iperf3')
            process.send_signal(signal.SIGINT)
            # print(process.communicate()[0])
            if popen_wait(process, timeout=1) is None:
                error('server popen did not exit correctly\n')
                process.kill()

        for process in client_tcpdumps:
            process.send_signal(signal.SIGINT)
            if popen_wait(process, timeout=1) is None:
                error('tcp_dump popen did not exit correctly\n')
                process.kill()

        time.sleep(1)
        # os.system('killall -9 iperf3')
        # os.system('killall -9 tcpdump')

        output('Done with experiment\n' + '.'*80 + '\n')

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
