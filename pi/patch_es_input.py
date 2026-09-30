#!/usr/bin/env python3
import argparse
import xml.etree.ElementTree as ET

CONFIGS = [
    ('AI Arcade Player 1', '030000000912000001a1000001000000'),
    ('AI Arcade Player 2', '030000000912000002a1000001000000'),
]
INPUTS = [
    ('up','axis','1','-1'), ('down','axis','1','1'),
    ('left','axis','0','-1'), ('right','axis','0','1'),
    ('a','button','0','1'), ('b','button','1','1'),
    ('x','button','2','1'), ('y','button','3','1'),
    ('pageup','button','4','1'), ('pagedown','button','5','1'),
    ('select','button','8','1'), ('start','button','9','1'),
]

def main():
    p = argparse.ArgumentParser()
    p.add_argument('path')
    args = p.parse_args()

    tree = ET.parse(args.path)
    root = tree.getroot()

    for name, guid in CONFIGS:
        for node in list(root.findall('inputConfig')):
            if node.get('deviceName') == name:
                root.remove(node)
        cfg = ET.SubElement(root, 'inputConfig', {
            'type': 'joystick', 'deviceName': name, 'deviceGUID': guid
        })
        for iname, itype, iid, value in INPUTS:
            ET.SubElement(cfg, 'input', {
                'name': iname, 'type': itype, 'id': iid, 'value': value
            })

    try:
        ET.indent(tree, space='  ')
    except AttributeError:
        pass
    tree.write(args.path, encoding='utf-8', xml_declaration=False)

if __name__ == '__main__':
    main()
