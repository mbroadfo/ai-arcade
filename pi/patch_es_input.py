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
# A USB keyboard for human mode, as a whole controller: the old cabinet's layout (Pi 3, set up by hand in
# EmulationStation), plus the triggers and thumb buttons it had only in RetroArch, and Escape as the hotkey. SDL2 key
# codes. pi/install.py hands this to RetroPie's inputconfiguration.sh, which writes the same keys into RetroArch (and
# the hotkey combinations: Escape+Enter quits a game, Escape+D opens RetroArch's menu, Escape+Q/W load/save state).
KEYBOARD = [
    ('up', '1073741906'), ('down', '1073741905'), ('left', '1073741904'), ('right', '1073741903'),
    ('a', '97'), ('b', '115'), ('x', '100'), ('y', '102'),            # A S D F
    ('start', '13'), ('select', '39'),                                # Enter, '
    ('pageup', '113'), ('pagedown', '119'),                           # Q W (EmulationStation's names for the shoulders)
    ('leftshoulder', '113'), ('rightshoulder', '119'),                # the same, by the names RetroArch's script reads
    ('lefttrigger', '101'), ('righttrigger', '114'),                  # E R
    ('leftthumb', '116'), ('rightthumb', '121'),                      # T Y
    ('leftanalogup', '117'), ('leftanalogdown', '105'),               # U I
    ('leftanalogleft', '111'), ('leftanalogright', '112'),            # O P
    ('rightanalogup', '91'), ('rightanalogdown', '93'),               # [ ]
    ('rightanalogleft', '92'), ('rightanalogright', '127'),           # \ Delete
    ('hotkeyenable', '27'),                                           # Escape
]


def keyboard_config(parent):
    keyboard = ET.SubElement(parent, 'inputConfig', {'type': 'keyboard', 'deviceName': 'Keyboard', 'deviceGUID': '-1'})
    for iname, key in KEYBOARD:
        ET.SubElement(keyboard, 'input', {'name': iname, 'type': 'key', 'id': key, 'value': '1'})
    return keyboard


def write(tree, path):
    try:
        ET.indent(tree, space='  ')
    except AttributeError:
        pass
    tree.write(path, encoding='utf-8', xml_declaration=False)

def main():
    p = argparse.ArgumentParser()
    p.add_argument('path')
    p.add_argument('--keyboard-only', action='store_true',
                   help='write a new file holding just the keyboard (the input inputconfiguration.sh reads)')
    args = p.parse_args()

    if args.keyboard_only:
        root = ET.Element('inputList')
        keyboard_config(root)
        write(ET.ElementTree(root), args.path)
        return

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
    keyboard_config(root)
    write(tree, args.path)

if __name__ == '__main__':
    main()
