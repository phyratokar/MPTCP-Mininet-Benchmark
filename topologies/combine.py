import os
import json
import glob

file_name = './visualizer/all_networks.json'

if os.path.exists(file_name):
    print('old file removed')
    os.remove(file_name)

files = glob.glob("./*.json")

data = {}
data['type'] = 'NetworkCollection'

network_list = []
for fn in files:
    print('reading file {}'.format(fn))
    with open(fn, 'r') as f:
        c = json.loads(f.read())
        c['type'] = c['topology_id']
        network_list.append(c)

data['collection'] = network_list
# print(data)


with open(file_name, 'w') as outfile:
    json.dump(data, outfile)
    print('new File generated')
