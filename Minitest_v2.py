import os
import time

from mininet.cli import CLI
from mininet.net import Mininet
from mininet.topo import Topo
from mininet.link import TCLink

from signal import SIGINT
import datetime


class SingleFlowTopo(Topo):
    """
    h1 --- s1 --- s2 --- h2
    """

    def build(self, q_size, delay):
        # Add hosts and switches
        h1 = self.addHost('h1')
        h2 = self.addHost('h2')
        s1 = self.addSwitch('s1')
        s2 = self.addSwitch('s2')

        # use_hfsc, use_tbf, use_htb, bw, delay, jitter, max_queue_size, loss
        # linkopts = dict(jitter='0ms', max_queue_size=q_size)  # loss=0

        # Add links
        self.addLink(h1, s1, bw=100, delay='0.1ms', jitter='0ms', max_queue_size=10)
        self.addLink(s1, s2, bw=10, delay='{}ms'.format(delay), jitter='0ms', max_queue_size=q_size)
        self.addLink(s2, h2, bw=100, delay='0.1ms', jitter='0ms', max_queue_size=10)


def main():
    runtime = 120
    ccs = ['lia'] # ['cubic', 'lia', 'olia', 'balia', 'wvegas']
    delays = [1, 25, 50, 75, 100]
    q_multipliers = [1, 1.2, 1.5, 2]

    num_exps = len(ccs) * len(delays) * len(q_multipliers)

    exp_runtime = (runtime + 1) * num_exps
    finish_time = datetime.datetime.now() + datetime.timedelta(seconds=exp_runtime)
    print('Expected Runtime:\t{}h\nExpected end of Experiments:\t{}'.format(exp_runtime/3600.0, finish_time))


    os.system('modprobe mptcp_balia; modprobe mptcp_wvegas; modprobe mptcp_olia; modprobe mptcp_coupled')
    os.system('sysctl -w net.mptcp.mptcp_enabled=1')
    os.system('sysctl -w net.mptcp.mptcp_path_manager=fullmesh')
    os.system('sysctl -w net.mptcp.mptcp_scheduler=default')

    for cc in ccs:
        os.system('sysctl -w net.ipv4.tcp_congestion_control={}'.format(cc))

        for delay in delays:
            for q_multiplier in q_multipliers:
                # Start Mininet
                rtt = 2 * delay
                q_size = int(q_multiplier * (rtt / 1000.0) * 10 / 8 * 1e6 / 1500)
                print('cc: {}, delay: {}, q_size: {}'.format(cc, delay, q_size))
                topo = SingleFlowTopo(q_size=q_size, delay=delay)
                net = Mininet(topo=topo, link=TCLink)

                net.start()
                time.sleep(1)

                # run bw and test ping
                src = net.get('h1')
                dst = net.get('h2')
                exp_name = '{}_{}q_{}rtt'.format(cc, q_size, rtt)

                ping_popen = src.popen('ping', dst.IP())
                dump_popen = src.popen('tcpdump', '-i', 'any', '-w', '{}_middleQ_dump.pcap'.format(exp_name), 'host', dst.IP())

                srv_tp, _ = net.iperf([src, dst], seconds=runtime)

                ping_popen.send_signal(SIGINT)
                dump_popen.send_signal(SIGINT)

                # out, _err = ping_popen.communicate()

                with open('{}_middleQ_log.txt'.format(exp_name), 'w') as f:
                    f.write('cc: {}\tdelay: {}\trtt: {}\tq_size: {}\n'.format(cc, delay, rtt, q_size))
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
