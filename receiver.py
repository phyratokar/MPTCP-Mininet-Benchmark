"""
Receiver python implementation receiving and discarding traffic from receiver.
Credit to Wen-Chien Chen and Kevin Han which implemented this:
https://bitbucket.org/iamtheone188/cs244-2015-wckh-mptcp/src/master/
https://reproducingnetworkresearch.wordpress.com/2015/05/31/cs-244-15-reproducing-the-3gwifi-application-level-latency-results-in-mptcp/
"""

from argparse import ArgumentParser
from struct import unpack
import socket
import sys
from monotonic import monotonic  # Monotonic time to avoid issues from NTP adjustments

# Parse arguments
parser = ArgumentParser(description="Receiver for MPTCP latency measurements")
parser.add_argument('--port', '-p', type=int, help="Port to listen on", required=True)
parser.add_argument('--size', type=int, help="Size of each packet in bytes", default=1428)
parser.add_argument('--outfile', '-o', help="Name of output file", required=True)
args = parser.parse_args()
# TODO: Should we set a receive buffer size?

format_string = "i%dx" % (args.size-4)  # 4 byte counter + padding


def main():
    try:
        f = open(args.outfile, 'w')
        f.write('pkt_id\trcv_t [s]\n')
    except IOError:
        sys.stderr.write("Could not open output file for writing\n")
        sys.exit(1)

    try:
        s = socket.socket(socket.AF_INET)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 32 * 1000)
        s.bind(('', args.port))  # Bind to all addresses
        s.listen(1)  # No concurrent connections
    except socket.error:
        sys.stderr.write("Could not bind receiver to port\n")
        sys.exit(1)

    print("Port binding successful; now listening for connections")
    conn, addr = s.accept()
    print("Established connection with %s" % addr[0])
    while True:
        data = conn.recv(args.size, socket.MSG_WAITALL)  # Return only when entire packet has been received
        timestamp = monotonic()
        if len(data) == 0:
            print("Connection closed")
            break
        counter = unpack(format_string, data)[0]
        f.write("{}\t{}\n".format(counter, timestamp))

    s.close()
    f.close()


if __name__ == '__main__':
    main()
