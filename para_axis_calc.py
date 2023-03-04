#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-only
#
# Coordinate Calculate for SPEF Mapping
#
# Copyright (C) 2023 Yeh, Hsin-Hsien <yhh76227@gmail.com>
#
import gzip
import os
import re
import sys

DESIGN_TOP = ""
INSTANCE, DEF_FILE = {}, {}
INST_MAX_LEN = COX_MAX_LEN = COY_MAX_LEN = FLIP_LEN_TYPE = 0

class Block:
#{{{
    def __init__(self, name, rot=False, co: list=None, di: list=None):
        self.name = name
        self.rot = rot
        self.co = [0, 0] if co is None else co
        self.di = [1, 1, 0, 0] if di is None else di
        self.sub_m = {}
#}}}

def config_parser(cfg_fp):
    """Configuration Parser"""  #{{{
    global DESIGN_TOP
    global INSTANCE, DEF_FILE
    global INST_MAX_LEN

    for line in open(cfg_fp):
        if line.startswith('#'):
            continue

        try:
            item, value = line.split('=')
        except ValueError:
            continue

        item, value = item.strip(), value.strip()

        if item == 'DESIGN_TOP':
            DESIGN_TOP = value
        elif item.startswith('INSTANCE'):
            INSTANCE[item[9:-1]] = value
            inst_len = len(item[9:-1])
            if inst_len > INST_MAX_LEN:
                INST_MAX_LEN = inst_len
        elif item.startswith('DEF_FILE'):
            DEF_FILE[item[9:-1]] = value
#}}}

def create_blk_tree(top: Block):
    """Create Block Tree"""  #{{{
    global COX_MAX_LEN, COY_MAX_LEN, FLIP_LEN_TYPE

    ## hierarchy check ## 

    lv_list, max_lv = [], 0

    for name in INSTANCE.keys():
        name_toks = name.split('/')
        lv = len(name_toks)
        if lv > max_lv:
            lv_list.extend([[]] * (lv - max_lv))
            max_lv = lv
        lv_list[lv-1].append(name_toks)

    ## make block tree ##

    for mod_list in lv_list:
        for name_toks in mod_list:
            node, name = top, name_toks[0]
            for tok in name_toks[1:]:
                if name in node.sub_m:
                    node = node.sub_m[name]
                    name = tok
                else:
                    name = '/'.join((name, tok))
            node.sub_m[name] = Block('/'.join(name_toks));

    ## calculate axis ##

    DE_CHK, UNIT, DIES, COMP_PRE, COMP_GO, FIN = tuple(range(6))
    coo_re = re.compile(r"\s*FIXED\s*\(\s*(\d+)\s+(\d+)\s*\)\s*(\w+)\s*")
    scan_stack = [top]

    while len(scan_stack) > 0:
        node = scan_stack.pop()
        if len(node.sub_m) != 0:
            scan_stack.extend(node.sub_m.values())

        mod_name = DESIGN_TOP if node.name == DESIGN_TOP else INSTANCE[node.name]

        try:
            def_fp = DEF_FILE[mod_name]
        except KeyError:
            print(f"WARNING: cannot find the def file of \'{mod_name}\'")
            sub_scan_stack = list(node.sub_m.values())
            while len(sub_scan_stack) > 0:
                sub_node = sub_scan_stack.pop()
                sub_node.co[:] = node.co[:]
                sub_node.di[0:2] = node.di[0:2]
                if len(sub_node.sub_m) != 0:
                    sub_scan_stack.extend(sub_node.sub_m.values())
            continue

        if os.path.splitext(def_fp)[1] == '.gz':
            f = gzip.open(def_fp, mode='rt')
        else:
            f = open(def_fp)

        stage, line = DE_CHK, f.readline()

        while line is not None:
            line = line.strip()
            if line != '':
                if stage == DE_CHK and line.startswith('DESIGN'):
                    while line[-1] != ';':
                        line += f.readline().strip()

                    if mod_name != line[:-1].split()[-1]:
                        raise SyntaxError(f"design name mismatch at {def_fp}")
                    else:
                        stage = UNIT

                elif stage == UNIT and line.startswith('UNITS'):
                    while line[-1] != ';':
                        line += f.readline().strip()

                    unit_val = float(line[:-1].split()[-1]) / 1000
                    stage = DIES

                elif stage == DIES and line.startswith('DIEAREA'):
                    while line[-1] != ';':
                        line += f.readline().strip()

                    m = re.findall(r'\(\s*\d+\s+\d+\s*\)', line[7:-1])
                    w, h = 0.0, 0.0

                    for coor in m:
                        x, y = [float(i) for i in coor[1:-1].split()]
                        if x > w:
                            w = x
                        if y > h:
                            h = y

                    node.co[0] += node.di[2] * round(w / unit_val)
                    node.co[1] += node.di[3] * round(h / unit_val)

                    cox_len, coy_len = [len(str(x)) for x in node.co[0:2]]
                    if cox_len > COX_MAX_LEN:
                        COX_MAX_LEN = cox_len
                    if coy_len > COY_MAX_LEN:
                        COY_MAX_LEN = coy_len

                    stage = COMP_PRE

                elif stage == COMP_PRE and line.startswith('COMPONENTS'):
                    sub_set = set(node.sub_m.keys())
                    if len(sub_set):
                        stage = COMP_GO
                    else:
                        break

                elif stage == COMP_GO:
                    if line.startswith('END'):
                        if len(sub_set) != 0:
                            for inst in sub_set:
                                print(f"WARNING: cannot find \'{inst}\' in {def_fp}")
                        break

                    cmd = line if line[0] == '-' else ' '.join((cmd, line))
                    if cmd[-1] == ';':
                        sub_cmd_list = cmd[1:-1].split('+')
                        inst = sub_cmd_list[0].split()[0]
                        if inst in sub_set:
                            sub_set.remove(inst)
                            is_done = False
                            for sub_cmd in sub_cmd_list[1:]:
                                if sub_cmd[1:].startswith('FIXED'):
                                    is_done = True
                                    m = coo_re.match(sub_cmd)
                                    sub_node = node.sub_m[inst]
                                    sub_node.co[0] = node.co[0] + node.di[0] * round(float(m[1]) / unit_val)
                                    sub_node.co[1] = node.co[1] + node.di[1] * round(float(m[2]) / unit_val)

                                    cox_len, coy_len = [len(str(x)) for x in sub_node.co[0:2]]
                                    if cox_len > COX_MAX_LEN:
                                        COX_MAX_LEN = cox_len
                                    if coy_len > COY_MAX_LEN:
                                        COY_MAX_LEN = coy_len

                                    if m[3] == 'N':
                                        FLIP_LEN_TYPE |= 3
                                        sub_node.di[0:2] = node.di[0:2]
                                    elif m[3] == 'S':
                                        FLIP_LEN_TYPE |= 3
                                        sub_node.di[0:2] = node.di[0] * -1, node.di[1] * -1
                                        sub_node.di[2:4] = node.di[0:2]
                                    elif m[3] == 'W':
                                        pass
                                    elif m[3] == 'E':
                                        pass
                                    elif m[3] == 'FN':
                                        FLIP_LEN_TYPE |= 1
                                        sub_node.di[0:2] = node.di[0] * -1, node.di[1]
                                        sub_node.di[2] = node.di[0]
                                    elif m[3] == 'FS':
                                        FLIP_LEN_TYPE |= 1
                                        sub_node.di[0:2] = node.di[0], node.di[1] * -1
                                        sub_node.di[3] = node.di[1]
                                    elif m[3] == 'FW':
                                        pass
                                    elif m[3] == 'FE':
                                        pass

                                    break

                            if not is_done:
                                print(f"WARNING: \'{inst}\' isn't fixed in {def_fp}")
                            if len(sub_set) == 0:
                                break

            line = f.readline()
        f.close()
#}}}

def print_blk_axis(top: Block):
    """Print Block Axis"""  #{{{
    inst_len = INST_MAX_LEN + 20
    flip_len = 9 if FLIP_LEN_TYPE == 3 else 6

    print()

    scan_stack = [top]
    while len(scan_stack) > 0:
        node = scan_stack.pop()

        if node.name != DESIGN_TOP:
            if node.di[0:2] == [1, 1]:
                flip_type = 'flip_none'
            elif node.di[0:2] == [1, -1]:
                flip_type = 'flip_x'
            elif node.di[0:2] == [-1, 1]:
                flip_type = 'flip_y'
            elif node.di[0:2] == [-1, -1]:
                flip_type = 'flip_both'

            print("{} \" -x_offset {} -y_offset {} -axis_flip {} \"".format(
                    f"set PARASITIC_AXIS({node.name})".ljust(inst_len),
                    str(node.co[0]).ljust(COX_MAX_LEN), 
                    str(node.co[1]).ljust(COY_MAX_LEN), 
                    flip_type.ljust(flip_len)))
        
        sub_m_list = list(node.sub_m.values())
        for i in range(len(sub_m_list)-1, -1, -1):
            scan_stack.append(sub_m_list[i])

    print()
#}}}

def main():
    """Main Function"""  #{{{
    if len(sys.argv) < 2:
        print("usage: {} <config_path>".format(os.path.basename(sys.argv[0])))
        exit(1)

    config_parser(sys.argv[1])
    top = Block(DESIGN_TOP)
    create_blk_tree(top)
    print_blk_axis(top)
#}}}

if __name__ == '__main__':
    main()

