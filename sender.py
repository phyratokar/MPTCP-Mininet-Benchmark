"""
Sender python implementation sending random traffic to receiver.
Credit to Wen-Chien Chen and Kevin Han which implemented this:
https://bitbucket.org/iamtheone188/cs244-2015-wckh-mptcp/src/master/
https://reproducingnetworkresearch.wordpress.com/2015/05/31/cs-244-15-reproducing-the-3gwifi-application-level-latency-results-in-mptcp/
"""
from argparse import ArgumentParser
from struct import pack
from time import sleep
import socket
import sys
from monotonic import monotonic  # Monotonic time to avoid issues from NTP adjustments

# Parse arguments
parser = ArgumentParser(description="Sender for MPTCP latency measurements")
parser.add_argument('--server', '-s', help="IP address of receiver", required=True)
parser.add_argument('--port', '-p', type=int, help="Port of receiver", required=True)
parser.add_argument('--size', type=int, help="Size of each packet in bytes", default=1428)
parser.add_argument('--time', '-t', type=int, help="Number of seconds to send for", default=600)
parser.add_argument('--bufsize', type=int, help="Send buffer size in KB", default=200)
parser.add_argument('--outfile', '-o', help="Name of output file", required=True)
args = parser.parse_args()

format_string = "i%dx" % (args.size-4)  # 4 byte counter


def main():
    try:
        f = open(args.outfile, 'w')
        f.write('pkt_id\tsnd_t [s]\tpayload [bytes]\n')
    except IOError:
        sys.stderr.write("Could not open output file for writing\n")
        sys.exit(1)

    try:
        s = socket.socket(socket.AF_INET)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, args.bufsize / 2 * 1000)  # The kernel doubles the value set here
        s.connect((args.server, args.port))
    except socket.error:
        sys.stderr.write("Could not connect to receiver\n")
        sys.exit(1)

    print("Connected to receiver")
    sleep(1) # Wait in case receiver needs to do some initial processing

    print("Starting packet flow")
    start_time = monotonic()
    counter = 1
    while monotonic() - start_time < args.time:
        packet = pack(format_string, counter)
        s.send(packet)
        timestamp = monotonic()
        f.write("{}\t{}\t{}\n".format(counter, timestamp, args.size))
        counter += 1
        # sleep(1)

    print("Shutting down")
    s.close()
    f.close()


if __name__ == '__main__':
    main()
