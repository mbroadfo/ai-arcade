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
# A USB keyboard for human mode: SDL2 key codes. Arrows move, Enter accepts, Backspace goes back, Space opens the
# menu, Right Shift is select, Page Up/Down page through lists. (In games RetroArch's own keyboard defaults apply.)
KEYBOARD = [
    ('up', '1073741906'), ('down', '1073741905'), ('left', '1073741904'), ('right', '1073741903'),
    ('a', '13'), ('b', '8'), ('start', '32'), ('select', '1073742053'),
    ('pageup', '1073741899'), ('pagedown', '1073741902'),
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

    for node in list(root.findall('inputConfig')):
        if node.get('type') == 'keyboard':
            root.remove(node)
    keyboard = ET.SubElement(root, 'inputConfig', {'type': 'keyboard', 'deviceName': 'Keyboard', 'deviceGUID': '-1'})
    for iname, key in KEYBOARD:
        ET.SubElement(keyboard, 'input', {'name': iname, 'type': 'key', 'id': key, 'value': '1'})

    try:
        ET.indent(tree, space='  ')
    except AttributeError:
        pass
    tree.write(args.path, encoding='utf-8', xml_declaration=False)

if __name__ == '__main__':
    main()
