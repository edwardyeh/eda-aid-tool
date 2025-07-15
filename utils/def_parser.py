#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-only
#
# Copyright (C) 2025 Yeh, Hsin-Hsien <yhh76227@gmail.com>
#
"""
DEF Parser for the Layout Check
"""
import collections
import datetime
import gzip
import re
import sys
from pathlib import Path


class DEFParser:
    """
    DEF parser for the layout check.
    """
    def __init__(self, def_file, is_proc_time_show: bool=False):
        self.def_file = Path(def_file)
        if not self.def_file.exists():
            raise OSError(f'Cannot find the DEF file ({self.def_file}).')
        self.def_dict = {}
        self.proc_time = {}
        self.is_proc_time_show = is_proc_time_show

    def parse_def(self, req_dict: dict):
        """
        Parse the DEF file.

        Parameters
        ----------
        req_dict : dict
            Parsing requirement for the layout check
        """
        if self.def_file.suffix == '.gz':
            fp = gzip.open(self.def_file, mode='rt')
        else:
            fp = open(self.def_file)

        self._proc_time_rec('START')

        while (line := fp.readline()) != '':
            line = line.split('#')[0].strip()
            if line == '':
                continue
            if line.startswith('END'):
                self._proc_time_rec(line)
                continue

            desc_list = line.split()
            if desc_list[0] == 'DESIGN':
                self.def_dict['design'] = desc_list[1]
                self._proc_time_rec('DESIGN')
            elif desc_list[0] == 'UNITS':
                self.def_dict['unit'] = {
                    'unit': desc_list[2],
                    'percision': int(desc_list[3])
                }
                self._proc_time_rec('UNITS')
            elif desc_list[0] == 'DIEAREA':
                self._parse_diearea(line)
                self._proc_time_rec('DIEAREA')
            elif desc_list[0] == 'NONDEFAULTRULES':
                self._parse_ndr(fp)
                self._proc_time_rec('NDR')
            elif desc_list[0] == 'COMPONENTS':
                self._parse_components(fp, req_dict['comp'])
                self._proc_time_rec('COMPONENTS')
            elif desc_list[0] == 'SPECIALNETS':
                pass
            elif desc_list[0] == 'NETS':
                self._parse_net(fp, req_dict['net'])
                self._proc_time_rec('NETS')
        fp.close()

    def _parse_diearea(self, desc: str):
        """Parsing die area."""
        # Get the corner coorderination list
        diearea = {'coor': [], 'cw': None, 't': [], 'b': [], 'l': [], 'r': []}

        coor_list = diearea['coor']
        for data in re.findall(r'\(\s*([-]*\d+)\s+([-]*\d+)\s*\)', desc):
            coor_list.append((int(data[0]), int(data[1])))

        # Get the winding order of the die area
        acc = 0
        for i in range(size:=len(coor_list)):
            i2 = (i + 1) % size
            acc += coor_list[i][0] * coor_list[i2][1] - \
                   coor_list[i2][0] * coor_list[i][1]

        prv_x, prv_y = coor_list[0]
        if acc < 0:
            diearea['cw'] = True
            # Get the boundary list
            for cur_x, cur_y in coor_list[1:]:
                if cur_x == prv_x:
                    if cur_y > prv_y:
                        diearea['l'].append((prv_x, cur_x, prv_y, cur_y))
                    else:
                        diearea['r'].append((cur_x, prv_x, cur_y, prv_y))
                else:
                    if cur_x > prv_x:
                        diearea['t'].append((prv_x, cur_x, prv_y, cur_y))
                    else:
                        diearea['b'].append((cur_x, prv_x, cur_y, prv_y))
                prv_x, prv_y = cur_x, cur_y
        else:
            diearea['cw'] = False
            # Get the boundary list
            for cur_x, cur_y in coor_list[1:]:
                if cur_x == prv_x:
                    if cur_y > prv_y:
                        diearea['r'].append((prv_x, cur_x, prv_y, cur_y))
                    else:                                
                        diearea['l'].append((cur_x, prv_x, cur_y, prv_y))
                else:
                    if cur_x > prv_x:
                        diearea['b'].append((prv_x, cur_x, prv_y, cur_y))
                    else:                                
                        diearea['t'].append((cur_x, prv_x, cur_y, prv_y))
                prv_x, prv_y = cur_x, cur_y

        self.def_dict['diearea'] = diearea

    def _parse_ndr(self, def_fp):
        """Parse non-default-rules."""
        ndr_dict = collections.defaultdict(dict)

        desc_toks = []
        while (line := def_fp.readline()) != '':
            line = line.split('#')[0].strip()
            if line == '':
                continue
            if line == 'END NONDEFAULTRULES':
                break

            desc_toks.extend(line.split())
            if desc_toks[-1] != ';':
                continue

            cmd_stack = []
            for tok in desc_toks:
                if tok in {'+', ';'}:
                    if cmd_stack[0] == '-':
                        ndr = ndr_dict[cmd_stack[1]]
                        ndr['style'] = 'SOFT'
                        ndr['layer'] = {}
                    elif cmd_stack[0] == 'HARDSPACING':
                        ndr['style'] = 'HARD'
                    elif cmd_stack[0] == 'LAYER':
                        layer = ndr['layer'].setdefault(cmd_stack[1], {})
                        for i in range(2, len(cmd_stack), 2):
                            layer[cmd_stack[i].lower()] = int(cmd_stack[i+1])
                    cmd_stack = []
                else:
                    cmd_stack.append(tok)
            desc_toks = []

        self.def_dict['ndr'] = ndr_dict

    def _parse_components(self, def_fp, req_comp: set):
        """Parse components."""
        comp_dict = collections.defaultdict(dict)
        req_num = -1 if req_comp is None else len(req_comp)
        
        desc_toks = []
        while (line := def_fp.readline()) != '':
            line = line.split('#')[0].strip()
            if line == '':
                continue
            if line == 'END COMPONENTS':
                break
            if req_num == 0:
                continue

            desc_toks.extend(line.split())
            if desc_toks[-1] != ';':
                continue

            cmd_stack = []
            for tok in desc_toks:
                if tok in {'+', ';'}:
                    if cmd_stack[0] == '-':
                        if req_num >= 0 and cmd_stack[1] not in req_comp:
                            break
                        req_num -= 1
                        comp = comp_dict[cmd_stack[1]]
                        comp['ref'] = cmd_stack[2]
                    elif cmd_stack[0] in {'FIXED', 'COVER', 'PLACED'}:
                        comp['sts'] = cmd_stack[0]
                        comp['pt'] = cmd_stack[2:4]
                        comp['ori'] = cmd_stack[5]
                    elif cmd_stack[0] == 'UNPLACED':
                        comp['sts'] = cmd_stack[0]
                    cmd_stack = []
                else:
                    cmd_stack.append(tok)
            desc_toks = []

        self.def_dict['comp'] = comp_dict

    def _parse_net(self, def_fp, req_net: set):
        """Parse components."""
        ROUTE_STATUS = {'COVER', 'FIXED', 'ROUTED', 'NOSHIELD', 'NEW'}
        ROUTE_ORIENT = {'N', 'S', 'W', 'E', 'FN', 'FS', 'FW', 'FE'}
        net_dict = collections.defaultdict(dict)
        req_num = -1 if req_net is None else len(req_net)
        
        desc_toks = [] 
        while (line := def_fp.readline()) != '':
            line = line.split('#')[0].strip()
            if line == '':
                continue
            if line == 'END NETS':
                break
            if req_num == 0:
                continue

            desc_toks.extend(line.split())
            if desc_toks[-1] != ';':
                continue

            cmd_stack = []
            for tok in desc_toks:
                if tok in {'+', ';'}:
                    try:
                        if cmd_stack[0] == '-':
                            if req_num >= 0 and cmd_stack[1] not in req_net:
                                break
                            req_num -= 1
                            net = net_dict[cmd_stack[1]]
                            pin = net.setdefault('pin', [])
                            for data in re.findall(r'\(\s*(\S+)\s+(\S+)\s*\)', 
                                                   ' '.join(cmd_stack)):
                                if data[0] == 'PIN':
                                    pin.append(('port', data[1]))
                                else:
                                    pin.append(('pin', '/'.join(data)))
                        elif cmd_stack[0] == 'SHIELDNET':
                            net['shield'] = cmd_stack[1]
                        elif cmd_stack[0] == 'NONDEFAULTRULE':
                            net['ndr'] = cmd_stack[1]
                        elif cmd_stack[0] in ROUTE_STATUS:
                            net['status'] = cmd_stack[0]
                            route_list = net.setdefault('route', [])
                            cmd_len, i = len(cmd_stack), 0
                            while i < cmd_len:
                                if cmd_stack[i] in ROUTE_STATUS:
                                    route_list.append(route:={})
                                    route['layer'], i = cmd_stack[i+1], (i + 2)
                                    if cmd_stack[i] == 'TAPER':
                                        route['taper'], i = 'default', (i + 1)
                                    elif cmd_stack[i] == 'TAPERRULE':
                                        route['taper'], i = cmd_stack[i+1], (i + 2)
                                    segment_list = route.setdefault('segment', [])
                                    pt1x = int(cmd_stack[i+1])
                                    pt1y = int(cmd_stack[i+2])
                                    if cmd_stack[i+3] == ')':
                                        pt1e, i = 0, (i + 4)
                                    else:
                                        pt1e, i = int(cmd_stack[i+3]), (i + 5)
                                elif cmd_stack[i] == '(':
                                    pt2x = pt1x if cmd_stack[i+1] == '*' else int(cmd_stack[i+1])
                                    pt2y = pt1y if cmd_stack[i+2] == '*' else int(cmd_stack[i+2])
                                    if cmd_stack[i+3] == ')':
                                        pt2e, i = 0, (i + 4)
                                    else:
                                        pt2e, i = int(cmd_stack[i+3]), (i + 5)
                                    if pt1x == pt2x and pt1y != pt2y:
                                        if pt1y > pt2y:
                                            pt1y += pt1e
                                            pt2y -= pt2e
                                            coor = [pt1x, pt2x, pt2y, pt1y]
                                        else:
                                            pt1y -= pt1e
                                            pt2y += pt2e
                                            coor = [pt1x, pt2x, pt1y, pt2y]
                                        segment_list.append({'type': 'rv', 'coor': coor})
                                    elif pt1x != pt2x and pt1y == pt2y:
                                        if pt1x > pt2x:
                                            pt1x += pt1e
                                            pt2x -= pt2e
                                            coor = [pt2x, pt1x, pt1y, pt2y]
                                        else:
                                            pt1x -= pt1e
                                            pt2x += pt2e
                                            coor = [pt1x, pt2x, pt1y, pt2y]
                                        segment_list.append({'type': 'rh', 'coor': coor})
                                    else:
                                        coor_x = [pt2x, pt1x] if pt1x > pt2x else [pt1x, pt2x]
                                        coor_y = [pt2y, pt1y] if pt1y > pt2y else [pt1y, pt2y]
                                        segment_list.append({'type': 'rd', 'coor': coor_x + coor_y})
                                else:
                                    segment = {
                                        'type': 'vi', 
                                        'coor': [pt1x, pt1y], 
                                        'name': cmd_stack[i]
                                    }
                                    if (i := i + 1) < cmd_len and cmd_stack[i] in ROUTE_ORIENT:
                                        segment['orient'], i = cmd_stack[i], (i + 1)
                                    segment_list.append(segment)
                        elif cmd_stack[0] == 'USE':
                            net['style'] = cmd_stack[1]
                        cmd_stack = []
                    except Exception as e:
                        print('Error Net     : {}'.format(net_name))
                        print('Error Command : {}'.format(cmd_stack))
                        print('Debug Info    : {}'.format([pt1x, pt2x, pt1y, pt2y, pt1e, pt2e]))
                else:
                    cmd_stack.append(tok)
            desc_toks = []

        self.def_dict['net'] = net_dict

    def _proc_time_rec(self, tag: str):
        now_time = datetime.datetime.now()
        if self.is_proc_time_show and len(self.proc_time):
            prev_time = list(self.proc_time.values())[0]
            print(f'[Process Time] {tag:20s}: {now_time - prev_time}')
        self.proc_time[tag] = now_time


    def debug_print(self):
        print('\n=== [Debug] ===\n')
        for k1, v1 in self.def_dict.items():
            if k1 in {'diearea', 'comp'}:
                print(f'=== {k1}:')
                for k2, v2 in v1.items():
                    print('{} {}: {}'.format('-' * 5, k2, v2))
            elif k1 == 'ndr':
                print(f'=== {k1}:')
                for k2, v2 in v1.items():
                    print('{} {}:'.format('-' * 5, k2))
                    for k3, v3 in v2.items():
                        if k3 == 'layer':
                            print('{} {}:'.format('-' * 7, k3))
                            for k4, v4 in v3.items():
                                print('{} {}: {}'.format('-' * 9, k4, v4))
                        else:
                            print('{} {}: {}'.format('-' * 7, k3, v3))
            elif k1 == 'net':
                print(f'=== {k1}:')
                for k2, v2 in v1.items():
                    print('{} {}:'.format('-' * 5, k2))
                    for k3, v3 in v2.items():
                        if k3 == 'pin':
                            print('{} {}:'.format('-' * 7, k3))
                            for data in v3:
                                print('{} {}'.format('-' * 9, data))
                        elif k3 == 'route':
                            print('{} {}:'.format('-' * 7, k3))
                            for route in v3:
                                print('{} '.format('-' * 9), end='')
                                seg = []
                                for k4, v4 in route.items():
                                    if k4 == 'segment':
                                        seg = v4
                                    else:
                                        print(f'{k4}: {v4}', end='')
                                print(', sgement: ')
                                for data in seg:
                                    print('{} {}'.format('-' * 11, data))
                        else:
                            print('{} {}: {}'.format('-' * 7, k3, v3))
            else:
                print(f'=== {k1}: {v1}')
        print()


if __name__ == '__main__':
    # for debug
    parser = DEFParser(sys.argv[1],
                       is_proc_time_show=True)
    start_time = datetime.datetime.now()
    parser.parse_def({
        'comp': {'U_INV_0', 'U_CLK_BUF_5'},
        'net':  None
    })
    end_time = datetime.datetime.now()
    parser.debug_print()
    print()
    print(f'[Total Process Time]: {end_time - start_time}')
    print()


