import json
import os
import shlex
import subprocess
import time

import numpy as np
from mininet.log import error
from mininet.util import errFail


MPTCP_CCS = ['lia', 'olia', 'balia', 'wvegas']


def check_system():
    """
    Ensure MPTCP kernel and correct version of Mininet are installed on system. Mininet mismatch prints warning while
    missing MPTCP functionalities or Mininet installation will raise exceptions.

    Note:   Using mininet verison 2.2.2 or older leads to issues when many experiments are run (many build ups and
            tear downs of miniet) because mininet nodes do not correctly close their Pseduo-TTY pipes.
                => https://github.com/mininet/mininet/issues/838
    """
    out = subprocess.check_output('mn --version', shell=True, stderr=subprocess.STDOUT)
    if not out.startswith('2.3.'):
        print('Attention, starting with Mininet version {}, for longer runs version 2.3.x is required!'.format(
            out.strip()))

    if not os.path.exists('/proc/sys/net/mptcp/'):
        raise OSError('MPTCP does not seem to be installed on the system, '
                      'please verify that the kernel supports MPTCP.')


def system_call(cmd, ignore_codes=None):
    try:
        retcode = subprocess.call(shlex.split(cmd))
        if retcode < 0:
            error('Child was terminated by signal {}\n'.format(-retcode))
        elif retcode > 0 and retcode not in ignore_codes:
            error('Child returned {}\n'.format(retcode))
    except OSError as e:
        error('Execution failed: {}\n'.format(e))


def get_system_available_congestioncontrol_algos():
    out, err, ret = errFail(['sysctl', '-n', 'net.ipv4.tcp_available_congestion_control'])
    return out.strip().split()


def popen_wait(popen_task, timeout=-1):
    delay = 1.0
    while popen_task.poll() is None and timeout > 0:
        time.sleep(delay)
        timeout += delay
    return popen_task.poll() is not None


def read_json(file_name):
    if not os.path.isfile(file_name):
        print('JSON topology file not found! {}'.format(file_name))
        exit(1)

    with open(file_name, 'r') as f:
        config = json.load(f)

    return config


def get_groups(config, group_field):
    return [link['properties'][group_field] for link in config['links'] if group_field in link['properties']]


def gen_groups(config, field):
    """
    Generate all links with a field group set and return tuple of link group and value.
    :param config:      Json config
    :param field:       name of filed to look at
    :return:            generated (group_name, value)
    """
    if field not in ['latency', 'bandwidth']:
        raise NotImplementedError(
            'Only latency and bandwidth groups currently supported, "{}" not recognized.'.format(field))

    group_field = field + '_group'
    for link in config['links']:
        if group_field in link['properties']:
            yield (link['properties'][group_field], link['properties'][field])


def extract_groups(config, group_field):
    """
    Get unique groups and the number of all links withing the union of all groups.
    :param config:      JSON config
    :param group_field: group name
    :return:            tuple (unique groups list, number of links in all groups)
    """
    if group_field not in ['latency_group', 'bandwidth_group']:
        raise NotImplementedError(
            'Only latency and bandwidth groups currently supported, "{}" not recognized.'.format(group_field))

    groups = get_groups(config, group_field)
    unique_groups = np.unique(groups)
    assert len(unique_groups) > 0, 'Failed to find any links belonging to a group "{}".'.format(group_field)
    if len(unique_groups) > 2:
        raise NotImplementedError(
            'Not yet supporting more than two latency/bandwidth groups for links. {}'.format(unique_groups))
    return unique_groups, len(groups)


def get_group_with_value(config, group_field):
    groups = list(gen_groups(config, group_field))
    group_set = set(groups)
    if len(group_set) != len(set((x[0] for x in groups))):
        raise RuntimeError(
            'Groups with multiple values encountered, only one value allowed per group. {}'.format(group_set))
    assert len(group_set) > 0, 'Failed to find any links belonging to a group "{}".'.format(group_field)
    if len(group_set) > 2:
        raise NotImplementedError(
            'Not yet supporting more than two latency/bandwidth groups for links. {}'.format(group_set))
    return sorted(list(group_set))
