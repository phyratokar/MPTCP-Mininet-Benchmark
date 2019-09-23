import os
import time

from mininet.cli import CLI
from mininet.net import Mininet
from mininet.topo import Topo
from mininet.link import TCLink

from signal import SIGINT
import datetime


class MultiFlowTopo(Topo):
    """
    h1 --- s1 --- s2 --- h2
    """
    HOST_IP = '10.0.{0}.{1}'
    HOST_MAC = '00:00:00:00:{0:02x}:{1:02x}'

    def build(self, q_size_a, q_size_b, delay_a, delay_b):
        # Add hosts and switches
        h1 = self.addHost('h1')
        h2 = self.addHost('h2')
        s1 = self.addSwitch('s1')
        s2 = self.addSwitch('s2')
        s3 = self.addSwitch('s3')
        s4 = self.addSwitch('s4')

        # use_hfsc, use_tbf, use_htb, bw, delay, jitter, max_queue_size, loss
        # linkopts = dict(jitter='0ms', max_queue_size=q_size)  # loss=0

        # Add links
        self.addLink(h1, s1, bw=100, delay='0.1ms', jitter='0ms', max_queue_size=20)
        self.addLink(h1, s3, bw=100, delay='0.1ms', jitter='0ms', max_queue_size=20)
        self.addLink(s1, s2, bw=10, delay='{}ms'.format(delay_a), jitter='0ms', max_queue_size=q_size_a)
        self.addLink(s3, s4, bw=10, delay='{}ms'.format(delay_b), jitter='0ms', max_queue_size=q_size_b)
        self.addLink(s2, h2, bw=100, delay='0.1ms', jitter='0ms', max_queue_size=20)
        self.addLink(s4, h2, bw=100, delay='0.1ms', jitter='0ms', max_queue_size=20)

    def _setup_routing_per_host(self, host):
        # Manually set the ip addresses of the interfaces
        host_id = int(host.name[1:])

        for i, intf_name in enumerate(host.intfNames()):
            ip = self.HOST_IP.format(i, host_id)
            gateway = self.HOST_IP.format(i, 0)
            mac = self.HOST_MAC.format(i, host_id)

            # set IP and MAC of host
            host.intf(intf_name).config(ip='{}/24'.format(ip), mac=mac)

    def setup_routing(self, net):
        for host in self.hosts():
            self._setup_routing_per_host(net.get(host))


def main():
    runtime = 30
    ccs = ['wvegas']  # ['cubic', 'lia', 'olia', 'balia', 'wvegas']
    delays_a = [10]  # [1, 25, 50, 75, 100]
    delays_b = [100]  # [1, 25, 50, 75, 100]
    q_multipliers = [2]  # [1, 1.2, 1.5, 2]

    num_exps = len(ccs) * len(delays_a) * len(delays_b) * len(q_multipliers)

    exp_runtime = (runtime + 1) * num_exps
    finish_time = datetime.datetime.now() + datetime.timedelta(seconds=exp_runtime)
    print('Expected Runtime:\t{}h\nExpected end of Experiments:\t{}'.format(exp_runtime/3600.0, finish_time))

    os.system('modprobe mptcp_balia; modprobe mptcp_wvegas; modprobe mptcp_olia; modprobe mptcp_coupled')
    os.system('modprobe tcp_vegas')
    os.system('sysctl -w net.mptcp.mptcp_enabled=1')
    os.system('sysctl -w net.mptcp.mptcp_path_manager=fullmesh')
    os.system('sysctl -w net.mptcp.mptcp_scheduler=default')

    for cc in ccs:
        os.system('sysctl -w net.ipv4.tcp_congestion_control={}'.format(cc))

        for delay_a in delays_a:
            for delay_b in delays_b:
                for q_multiplier in q_multipliers:
                    # Start Mininet
                    rtt_a = 2 * delay_a
                    rtt_b = 2 * delay_b
                    q_size_a = int(q_multiplier * (rtt_a / 1000.0) * 10 / 8 * 1e6 / 1500) + 20
                    q_size_b = int(q_multiplier * (rtt_b / 1000.0) * 10 / 8 * 1e6 / 1500) + 20
                    print('cc: {}, delay_a: {}, q_size_a: {}, delay_b: {}, q_size_b: {}'.format(
                        cc, delay_a, q_size_a, delay_b, q_size_b))
                    topo = MultiFlowTopo(q_size_a=q_size_a, delay_a=delay_a, q_size_b=q_size_b, delay_b=delay_b)
                    net = Mininet(topo=topo, link=TCLink)
                    topo.setup_routing(net)

                    net.start()
                    time.sleep(1)

                    # run bw and test ping
                    src = net.get('h1')
                    dst = net.get('h2')
                    exp_name = '{}_{}q_{}rtt'.format(cc, '{}-{}'.format(q_size_a, q_size_b), '{}-{}'.format(rtt_a, rtt_b))

                    ping_popen = src.popen('ping', dst.IP())
                    dump_popen = src.popen('tcpdump', '-i', 'any', '-w', '{}_dump.pcap'.format(exp_name), 'host', dst.IP())

                    links = net.get('s1').connectionsTo(net.get('s2'))

                    dst_iperf = dst.popen('iperf3', '-s')
                    time.sleep(1)
                    src_iperf = src.popen('iperf3', '-c' '10.0.0.2', '-t', '20', '-C', cc)

                    # time.sleep(10)
                    # links[0][0].config(bw=10, delay='{}ms'.format(delay), jitter='0ms')
                    # links[0][1].config(bw=10, delay='{}ms'.format(delay), jitter='0ms')

                    out, err = src_iperf.communicate()
                    dst_iperf.terminate()
                    srv_tp = out.replace('iperf Done.', '').strip().splitlines()[-1].split()[6]
                    print(out)

                    # srv_tp, _ = net.iperf([src, dst], seconds=runtime)

                    ping_popen.send_signal(SIGINT)
                    dump_popen.send_signal(SIGINT)

                    # out, _err = ping_popen.communicate()
                    print('\t\t\t\t\t{} reached: \t{} Mbps'.format(cc, srv_tp))

                    with open('{}_middleQ_log.txt'.format(exp_name), 'w') as f:
                        f.write('cc: {}\tdelay: {}-{}\trtt: {}-{}\tq_size: {}-{}\n'.format(
                            cc, delay_a, delay_b, rtt_a, rtt_b, q_size_a, q_size_b))
                        f.write('tp: {}\n\n\n'.format(srv_tp))
                        out, err = ping_popen.communicate()
                        f.write(out)
                        f.write(err)

                    # print(out)
                    print('tp: {}'.format(srv_tp))

                    # CLI(net)

                    net.stop()


if __name__ == '__main__':
    try:
        main()
    except:
        print("-"*80)
        import traceback
        traceback.print_exc()
        os.system("killall -9 top bwm-ng tcpdump cat mnexec iperf iperf3; mn -c")
