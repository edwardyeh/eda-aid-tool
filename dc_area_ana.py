#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-only
#
# Design Compiler Area Report Analysis
#
# Copyright (C) 2022 Yeh, Hsin-Hsien <yhh76227@gmail.com>
#
import argparse
import copy
import gzip
import math
import os
import re
import sys
import textwrap
from dataclasses import dataclass, field

### Global Parameter ###  

#{{{
VERSION = '0.12.0'
DEFAULT_PATH_COL_SIZE = 32
DEFAULT_AREA_COL_SIZE = 9
ISYM = f"{0x251c:c}{0x2500:c}"
ESYM = f"{0x2514:c}{0x2500:c}"
BSYM = f"{0x2502:c} "

hide_op = {
        '>' : lambda a, b: a > b,
        '<' : lambda a, b: a < b,
        '==': lambda a, b: a == b,
        '>=': lambda a, b: a >= b,
        '<=': lambda a, b: a <= b
        }

# at: area total
# pt: percent total
hide_cmp = {
        'at': lambda node, op, val: hide_op[op](node.total_area, val),
        'pt': lambda node, op, val: hide_op[op](node.total_percent, val)
        }


design_list = []
level_list = []
root_list = []
tag_dict = {}
sum_dict = {}
#}}}

### Class Defintion ###

@dataclass (slots=True)
class UnitAttr:
#{{{
    value: float = 1
    tag:   str   = ''
    type:  int   = 0
#}}}

@dataclass(slots=True)
class TableAttr:
#{{{
    area_fs:       str
    ratio:         float
    unit:          UnitAttr
    dec_place:     int
    is_show_ts:    bool
    is_brief:      bool
    is_logic_sep:  bool
    is_reorder:    bool
    is_show_level: bool
    is_nosplit:    bool
    view_type:     str
    trace_root:    str
    is_verbose:    bool = False
    is_sub_sum:    bool = field(init=False, default=False)
    path_col_size: int  = DEFAULT_PATH_COL_SIZE
    is_cmp_pr:     bool = False
    base_design:   int  = 0
    cmp_type:      int  = 0
    design_name:   list = field(default_factory=list)
#}}}

@dataclass (slots=True)
class SumGroup:
#{{{
    name:       str
    total_area: int = 0
    comb_area:  int = 0
    seq_area:   int = 0
    bbox_area:  int = 0
    diff_area:  int = 0
#}}}

class Node:
#{{{
    def __init__(self, dname: str, bname: str, level: int, 
                 total_area: float, comb_area: float, seq_area: float, bbox_area: float,
                 parent=None, childs=None, scans=None):
        self.dname      = dname
        self.bname      = bname
        self.level      = level
        self.total_area = total_area
        self.comb_area  = comb_area
        self.seq_area   = seq_area
        self.bbox_area  = bbox_area
        self.parent     = parent
        self.childs     = set() if childs is None else childs
        self.scans      = set() if scans is None else sncas

        self.total_percent = -1
        self.is_show       = False
        self.is_hide       = False
        self.is_sub_root   = False
        self.gid           = None
        self.sub_comb_area = None
        self.sub_seq_area  = None
        self.sub_bbox_area = None
#}}}

class Design:
#{{{
    # def __init__(self, name: str):
    def __init__(self):
        # self.name = name
        self.total_area = 0
        self.bbox_area = 0
        self.path_len = 0
        self.top_node = None
        self.node_dict = {}
        self.diff_dict = {}
#}}}

### Sub Function ###

def load_area(area_fps, proc_mode: str, table_attr: TableAttr):  
    """Load area report"""  #{{{
    global design_list

    area_ratio = table_attr.ratio
    area_unit = table_attr.unit.value
    is_verbose = table_attr.is_verbose

    if type(area_fps) is not list:
        area_fps = [area_fps]

    for fid, area_fp in enumerate(area_fps, start=0):
        table_attr.design_name.append(f'Design{fid}')
        design_list.append(design:=Design())
        node_dict = design.node_dict
        top_node = None
        fsm = max_path_len = total_bbox_area = 0

        with open(area_fp) as f:
            line = f.readline()
            while line:
                if fsm == 2 and len(toks:=line.split()):
                    if toks[0].startswith("---"):
                        design.total_area = top_node.total_area
                        design.bbox_area = total_bbox_area
                        design.path_len = max_path_len 
                        design.top_node = top_node
                        break

                    path = toks[0]
                    del toks[0]

                    names = path.split('/')
                    dname = '/'.join(names[:-1])  # dirname
                    bname = names[-1]             # basename

                    if len(toks) == 0:  # total area
                        line = f.readline()
                        toks = line.split()
                    total_area = float(toks[0]) * area_ratio / area_unit
                    del toks[0]

                    if len(toks) == 0:  # total percent
                        line = f.readline()
                        toks = line.split()
                    del toks[0]

                    if len(toks) == 0:  # combination area
                        line = f.readline()
                        toks = line.split()
                    comb_area = float(toks[0]) * area_ratio / area_unit
                    del toks[0]

                    if len(toks) == 0:  # sequence area
                        line = f.readline()
                        toks = line.split()
                    seq_area = float(toks[0]) * area_ratio / area_unit
                    del toks[0]

                    if len(toks) == 0:  # bbox area
                        line = f.readline()
                        toks = line.split()
                    bbox_area = float(toks[0]) * area_ratio / area_unit
                    del toks[0]

                    total_bbox_area += bbox_area

                    if top_node is None:
                        top_node = node = Node(dname, bname, 0, total_area, comb_area, seq_area, bbox_area)
                        top_node.total_percent = 1.0
                    elif len(names) == 1:
                        node = Node(dname, bname, 1, total_area, comb_area, seq_area, bbox_area, parent=top_node)
                        node.total_percent = total_area / top_node.total_area
                        top_node.childs.add(node)
                    else:
                        parent_node = node_dict[dname]
                        node = Node(dname, bname, len(names), total_area, comb_area, seq_area, bbox_area, 
                                    parent=parent_node)
                        node.total_percent = total_area / top_node.total_area
                        parent_node.childs.add(node)

                    node_dict[path] = node

                    if is_verbose:
                        node.is_show = True
                        node.scans = node.childs

                    if table_attr.view_type == 'tree':
                        path_len = len(node.bname) + node.level * 2
                    elif table_attr.view_type == 'inst':
                        path_len = len(node.bname)
                    else:
                        path_len = len(node.dname) + len(node.bname) + 1

                    if path_len > max_path_len:
                        max_path_len = path_len

                elif fsm == 1:
                    if line.strip().startswith("---"):
                        fsm = 2

                elif fsm == 0:
                    if line.strip().startswith("Hierarchical cell"):
                        fsm = 1

                line = f.readline()
#}}}

def load_cfg(cfg_fp, design: Design, table_attr: TableAttr):
    """Load configuration"""  #{{{
    global level_list, sum_dict

    node_dict = design.node_dict
    max_lv = -1

    with open(cfg_fp) as f:
        line_no = 0
        for line in f.readlines():
            line_no += 1
            toks = line.split()
            if len(toks):
                if toks[0][0] == '#':
                    continue

                if toks[0].startswith('grp:'):
                    line, *_ = line.split('#')
                    group, name = line.split(':')
                    gid = 0 if group.strip() == 'grp' else int(group.strip()[3:])
                    name = name.strip('\"\'\n ')
                    if gid not in sum_dict:
                        sum_dict[gid] = SumGroup(name)
                    else:
                        sum_dict[gid].name = name
                    continue

                if toks[0].startswith('default_path_len:'):
                    line, *_ = line.split('#')
                    _, path_len = line.split(':')
                    path_len = int(path_len)
                    table_attr.path_col_size = path_len if path_len > 10 else 10
                    continue

                if toks[0].startswith('design_name:'):
                    line, *_ = line.split('#')
                    _, name_list = line.split(':')
                    for item in name_list.strip().split():
                        idx, name = item.split('-')
                        try:
                            table_attr.design_name[int(idx)] = name
                        except Exception:
                            pass
                    continue

                if toks[0].startswith('tag:'):
                    line, *_ = line.split('#')
                    inst_name, tag_name = line.split(':')[1].split()
                    tag_dict[inst_name] = tag_name
                    continue

                ## Load node from configuration

                node_list = []
                cmd_list = []

                if toks[0].startswith('re:'):
                    _, pattern, *cmds = re.split("re:\s*|\s", line)
                    regex = re.compile(pattern)
                    for path in node_dict.keys():
                        if regex.match(path) is not None:
                            node_list.append(node_dict[path])
                    cmd_list.extend(cmds)
                else:
                    try:
                        node_list.append(node_dict[toks[0]])
                    except KeyError as e:
                        print(f"\nCONFIG_ERROR: cell not found ({toks[0]}).\n")
                        exit(1)
                    cmd_list.extend(toks[1:])

                for node in node_list:
                    try:
                        node.is_show = True

                        if max_lv < node.level:
                            level_list.extend([set() for i in range(node.level - max_lv)])
                            max_lv = node.level

                        level_list[node.level].add(node)
                    except Exception as e:
                        print("-" * 60)
                        print("ConfigParseError: (line: {})".format(line_no))
                        print("unexisted path in the list.")
                        print("-" * 60)
                        raise e

                    ## Load command from configuration

                    try:
                        sub_max_lv = parse_cmd(node, cmd_list, table_attr)
                    except Exception as e:
                        print("-" * 60)
                        print("ConfigParseError: (line: {})".format(line_no))
                        print("error command.")
                        print("-" * 60)
                        raise e

                    if sub_max_lv > max_lv:
                        max_lv = sub_max_lv

    ## Backward scan link

    for level in range(max_lv, 0, -1):
        for node in level_list[level]:
            if node.parent is not None:
                if table_attr.is_verbose:
                    node.parent.is_show = True
                node.parent.scans.add(node)
                level_list[level-1].add(node.parent)
#}}}

def parse_cmd(node: Node, cmd_list: list, table_attr: TableAttr) -> int:
    """Parsing command"""  #{{{
    ## return: max_lv
    global root_list, sum_dict

    idx = max_lv = 0
    end_cond = len(cmd_list)

    while idx < end_cond:
        cmd = cmd_list[idx]
        idx += 1

        if cmd == '':
            continue
        if cmd[0] == '#':
            break

        if cmd.startswith('add') or cmd.startswith('sub') :
            toks = cmd.split(':')
            gid = 0 if len(toks[0]) == 3 else int(toks[0][3:])
            node.gid = gid if toks[0][0:3] == 'add' else -gid - 1
            if gid not in sum_dict:
                sum_dict[gid] = SumGroup(f'Group {gid}')
            if len(toks) > 1:
                name = toks[1]
                if name.startswith('\"'):
                    while not name.endswith('\"'):
                        name += f" {cmd_list[idx]}"
                        idx += 1
                elif name.startswith('\''):
                    while not name.endswith('\''):
                        name += f" {cmd_list[idx]}"
                        idx += 1
                sum_dict[gid].name = name.strip('\"\'\n ')
        elif cmd.startswith('hide'):
            toks = cmd.split(':')
            try:
                if toks[0] != 'hide':
                    raise SyntaxError("error command")
                elif len(toks) == 1:
                    node.is_hide = True
                else:
                    pat = toks[1]
                    if pat.startswith('\"'):
                        while not pat.endswith('\"'):
                            pat += f" {cmd_list[idx]}"
                            idx += 1
                    elif pat.startswith('\''):
                        while not pat.endswith('\''):
                            pat += f" {cmd_list[idx]}"
                            idx += 1
                    pat = pat.strip('\"\'\n ')

                    try:
                        ma = re.fullmatch("(\w+)\s*([><=]+)\s*(\w+)", pat)
                        if ma is None or len(ma_grp:=ma.groups()) != 3:
                            raise SyntaxError
                        else:
                            node.is_hide = hide_cmp[ma_grp[0]](node, ma_grp[1], float(ma_grp[2]))
                    except Exception as e:
                        print("ERR: error command syntax (cmd: hide)")
                        raise e
            except Exception as e:
                raise e
        elif cmd == 'sum':
            sub_area_sum(node)
            table_attr.is_sub_sum = True
        elif cmd == 'sr':
            node.is_sub_root = True
            root_list.append(node)
        elif cmd == 'inf':
            max_lv = trace_sub_node(node, 'inf', cmd_list[idx:], table_attr)
        elif cmd[0] == 'l':
            max_lv = trace_sub_node(node, cmd[1:], cmd_list[idx:], table_attr)
        else:
            raise SyntaxError("error command")

    return max_lv
#}}}

def trace_sub_node(cur_node: Node, trace_lv: str, cmd_list: list, table_attr: TableAttr) -> int:
    """Trace sub nodes"""  #{{{
    ## return: max_lv
    global level_list
    scan_lv = math.inf if trace_lv == 'inf' else cur_node.level + int(trace_lv)
    max_lv = len(level_list) - 1
    scan_stack = []

    if cur_node.level < scan_lv:
        cur_node.scans = cur_node.childs
        scan_stack.extend(cur_node.childs)

    while len(scan_stack):
        node = scan_stack.pop()
        node.is_show = True
        parse_cmd(node, cmd_list, table_attr)

        if max_lv < node.level:
            level_list.extend([set() for i in range(node.level - max_lv)])
            max_lv = node.level

        level_list[node.level].add(node)

        if node.level < scan_lv:
            node.scans = node.childs
            scan_stack.extend(node.childs)

    return max_lv
#}}}

def sub_area_sum(cur_node: Node):
    """Trace and Sum sub-node area"""  #{{{
    sub_comb_area = sub_seq_area = sub_bbox_area = 0
    scan_stack = [cur_node]

    while len(scan_stack):
        node = scan_stack.pop()
        sub_comb_area += node.comb_area
        sub_seq_area  += node.seq_area
        sub_bbox_area += node.bbox_area
        scan_stack.extend(node.childs)

    cur_node.sub_comb_area = sub_comb_area
    cur_node.sub_seq_area = sub_seq_area
    cur_node.sub_bbox_area = sub_bbox_area
#}}}

def show_hier_area(root_list: list, design: Design, table_attr: TableAttr):
    """Show hierarchical area"""  #{{{

    ## Group sum and remove hide node

    global level_list
    max_path_len = max_area = 0
    max_gid = -1

    for level in range(len(level_list)-1, -1, -1):
        for node in level_list[level]:
            if node.gid is not None:
                if node.sub_bbox_area is not None:
                    node_comb = node.sub_comb_area
                    node_seq  = node.sub_seq_area
                    node_bbox = node.sub_bbox_area
                else:
                    node_comb = node.comb_area
                    node_seq  = node.seq_area
                    node_bbox = node.bbox_area

                if node.gid >= 0:
                    sum_group = sum_dict[(gid := node.gid)]
                    sum_group.total_area += node.total_area
                    sum_group.comb_area  += node_comb
                    sum_group.seq_area   += node_seq
                    sum_group.bbox_area  += node_bbox
                else:
                    sum_group = sum_dict[(gid := abs(node.gid+1))]
                    sum_group.total_area -= node.total_area
                    sum_group.comb_area  -= node_comb
                    sum_group.seq_area   -= node_seq
                    sum_group.bbox_area  -= node_bbox

                if gid > max_gid:
                    max_gid = gid

            if node.is_hide or not node.is_show:
                if len(node.scans) == 0 and node.parent is not None:
                    node.parent.scans.remove(node)
                else:
                    node.is_show = False
            else:
                if table_attr.view_type == 'tree':
                    path_len = len(node.bname) + node.level * 2
                elif table_attr.view_type == 'inst':
                    path_len = len(node.bname)
                else:
                    path_len = len(node.dname) + len(node.bname) + 1

                if len(tag_dict) != 0 and table_attr.view_type != 'tree':
                    inst_path = node.bname if node.level < 2 else '/'.join((node.dname, node.bname))
                    if inst_path in tag_dict:
                        path_len = len(tag_dict[inst_path])

                if path_len > max_path_len:
                    max_path_len = path_len

                if node.total_area > max_area:
                    max_area = node.total_area

    if len(level_list) == 0:  # norm mode
        max_path_len = design.path_len
        max_area = design.total_area

    ## Show area report

    path_len = max_path_len + 5 if table_attr.is_show_level else max_path_len

    if table_attr.view_type == 'path' and not table_attr.is_nosplit:
        path_len = table_attr.path_col_size
    elif path_len < table_attr.path_col_size:
        path_len = table_attr.path_col_size

    if len(sum_dict):
        for gid, group in sum_dict.items():
            gid_len = 0 if gid == 0 else int(math.log10(gid))
            grp_len = len(group.name) + gid_len + 3
            if path_len < grp_len:
                path_len = grp_len

    if max_area == 0:
        area_len = 0
    else:
        area_len = int(math.log10(math.ceil(max_area))) + 2 + table_attr.dec_place
        area_len += len(table_attr.unit.tag)

    if table_attr.is_show_ts:
        area_len += int(math.log(max_area) / math.log(1000))
    if table_attr.is_sub_sum and not table_attr.is_brief:
        area_len += 2
    if area_len < DEFAULT_AREA_COL_SIZE:
        area_len = DEFAULT_AREA_COL_SIZE 

    print()
    show_divider(path_len, area_len, table_attr)
    show_header(path_len, area_len, table_attr)
    show_divider(path_len, area_len, table_attr)

    area_fs = table_attr.area_fs
    unit_val = table_attr.unit.value
    unit_tag = table_attr.unit.tag
    unit_type = table_attr.unit.type

    for root_idx, root_node in enumerate(root_list):
        if root_idx > 0:
            print()

        scan_stack = [root_node]
        sym_list = []

        while len(scan_stack):
            node = scan_stack.pop()
            if node.sub_bbox_area is not None:
                node_comb = node.sub_comb_area
                node_seq  = node.sub_seq_area
                node_bbox = node.sub_bbox_area
            else:
                node_comb = node.comb_area
                node_seq  = node.seq_area
                node_bbox = node.bbox_area

            node_total = node.total_area
            node_logic = node_comb  + node_seq
            node_area  = node_logic + node_bbox

            if table_attr.trace_root == 'sub':
                total_percent = node.total_area / root_node.total_area
            else:
                total_percent = node.total_percent

            try:
                bbox_percent = node_bbox / node_area
            except ZeroDivisionError as e:
                if node_bbox == 0:
                    bbox_percent = 0
                else:
                    raise e

            if table_attr.view_type == 'tree':
                try:
                    if node is root_node:
                        sym = ""
                    elif scan_stack[-1].level < node.level:
                        sym = "".join(sym_list + [ESYM])
                        if len(node.scans):
                            sym_list.append("  ")
                        else:
                            sym_list = sym_list[:scan_stack[-1].level - node.level]
                    else:
                        for idx in range(len(scan_stack)-1, -1, -1):
                            next_node = scan_stack[idx]
                            if next_node.level == node.level and not next_node.is_hide:
                                sym = "".join(sym_list + [ISYM]) 
                                break
                            elif next_node.level < node.level:
                                sym = "".join(sym_list + [ESYM])
                                break
                        else:
                            sym = "".join(sym_list + [ESYM])

                        if len(node.scans):
                            sym_list.append(BSYM)
                except Exception:
                    sym = "".join(sym_list + [ESYM])
                    if len(node.scans):
                        sym_list.append("  ")

                path_name = "".join((sym, node.bname))
            elif node.level < 2 or table_attr.view_type == 'inst':
                path_name = node.bname
            else:
                path_name = '/'.join((node.dname, node.bname))

            if len(tag_dict) != 0 and table_attr.view_type != 'tree':
                inst_path = node.bname if node.level < 2 else '/'.join((node.dname, node.bname))
                if inst_path in tag_dict:
                    path_name = tag_dict[inst_path]

            if table_attr.is_show_level:
                path_name = f"({node.level:2d}) " + path_name

            if node.gid is not None:
                if node.gid >= 0:
                    star = ' *{}+'.format(gid := node.gid)
                else:
                    star = ' *{}-'.format(gid := abs(node.gid+1))

                if gid > max_gid:
                    max_gid = gid
            else:
                star = ''

            if not node.is_show and table_attr.trace_root == 'leaf':
                pass
            else:
                if len(path_name) > path_len:
                    print(f"{path_name.ljust(path_len)}")
                    print(f"{' ' * path_len}", end='')
                else:
                    print(f"{path_name.ljust(path_len)}", end='')

                if node.sub_bbox_area is not None:
                    bk = ['(', ')', ' ']
                elif table_attr.is_sub_sum:
                    bk = [' '] * 3
                else:
                    bk = [''] * 3

                if table_attr.is_brief:
                    if node.is_show:
                        area_list = node_total
                        unit_cnt = 1

                        if unit_type == 2:
                            while area_list >= unit_val:
                                area_list /= unit_val
                                unit_cnt += 1

                        print("  {}  {} {}".format(
                                area_fs.format(area_list, unit_tag*unit_cnt, ['']*2).rjust(area_len),
                                f"{total_percent:.1%}".rjust(7),
                                star))
                    else:
                        print("  {}  {}".format(f"-".rjust(area_len),
                                                f"-".rjust(7)))
                elif table_attr.is_logic_sep:
                    if node.is_show:
                        area_list = [node_total, node_comb, node_seq, node_bbox]
                        unit_cnt = [1] * 4

                        if unit_type == 2:
                            for i in range(0, 4):
                                while area_list[i] >= unit_val:
                                    area_list[i] /= unit_val
                                    unit_cnt[i] += 1

                        print("  {}  {}  {}  {}  {}  {} {}".format(
                                area_fs.format(area_list[0], unit_tag*unit_cnt[0], ['']*2).rjust(area_len),
                                f"{total_percent:.1%}".rjust(7),
                                area_fs.format(area_list[1], unit_tag*unit_cnt[1], bk).rjust(area_len),
                                area_fs.format(area_list[2], unit_tag*unit_cnt[2], bk).rjust(area_len),
                                area_fs.format(area_list[3], unit_tag*unit_cnt[3], bk).rjust(area_len),
                                f"{bbox_percent:.1%}".rjust(7),
                                star))
                    else:
                        print("  {}  {}  {}  {}  {}  {}".format(f"-".rjust(area_len),
                                                                f"-".rjust(7),
                                                                f"-{bk[2]}".rjust(area_len),
                                                                f"-{bk[2]}".rjust(area_len),
                                                                f"-{bk[2]}".rjust(area_len),
                                                                f"-".rjust(7)))
                elif node.is_show:
                    area_list = [node_total, node_logic, node_bbox]
                    unit_cnt = [1] * 3

                    if unit_type == 2:
                        for i in range(0, 3):
                            while area_list[i] >= unit_val:
                                area_list[i] /= unit_val
                                unit_cnt[i] += 1

                    print("  {}  {}  {}  {}  {} {}".format(
                            area_fs.format(area_list[0], unit_tag*unit_cnt[0], ['']*2).rjust(area_len),
                            f"{total_percent:.1%}".rjust(7),
                            area_fs.format(area_list[1], unit_tag*unit_cnt[1], bk).rjust(area_len),
                            area_fs.format(area_list[2], unit_tag*unit_cnt[2], bk).rjust(area_len),
                            f"{bbox_percent:.1%}".rjust(7),
                            star))
                else:
                    print("  {}  {}  {}  {}  {}".format(f"-".rjust(area_len),
                                                        f"-".rjust(7),
                                                        f"-{bk[2]}".rjust(area_len),
                                                        f"-{bk[2]}".rjust(area_len),
                                                        f"-".rjust(7)))

            if table_attr.is_reorder:
                scan_stack.extend(sorted(node.scans, key=lambda x:x.total_area))
            else:
                scan_stack.extend(sorted(node.scans, key=lambda x:x.bname, reverse=True))

    if len(sum_dict) != 0:
        print()
        show_divider(path_len, area_len, table_attr)
        show_header(path_len, area_len, table_attr, title='Group')
        show_divider(path_len, area_len, table_attr)

        group_len = 1 if max_gid <= 0 else int(math.log10(max_gid)) + 1
        bk = ([' '] if table_attr.is_sub_sum else ['']) * 2

        for gid, sum_group in sorted(sum_dict.items()):
            sum_bbox_percent = 0 if sum_group.total_area == 0 else sum_group.bbox_area / sum_group.total_area
            sum_total_percent = sum_group.total_area / root_node.total_area

            if table_attr.is_brief:
                area_list = sum_group.total_area
                unit_cnt = 1
                if unit_type == 2:
                    while area_list >= unit_val:
                        area_list /= unit_val
                        unit_cnt += 1

                print("{}{}  {}  {}".format(
                        f"{gid}: ".rjust(group_len+2),
                        f"{sum_group.name}".ljust(path_len-group_len-2),
                        area_fs.format(area_list, unit_tag*unit_cnt, ['']*2).rjust(area_len),
                        f"{sum_total_percent:.1%}".rjust(7)))
            elif table_attr.is_logic_sep:
                area_list = [sum_group.total_area, sum_group.comb_area, sum_group.seq_area, 
                             sum_group.bbox_area]
                unit_cnt = [1] * 4

                if unit_type == 2:
                    for i in range(0, 4):
                        while area_list[i] >= unit_val:
                            area_list[i] /= unit_val
                            unit_cnt[i] += 1

                print("{}{}  {}  {}  {}  {}  {}  {}".format(
                        f"{gid}: ".rjust(group_len+2),
                        f"{sum_group.name}".ljust(path_len-group_len-2),
                        area_fs.format(area_list[0], unit_tag*unit_cnt[0], ['']*2).rjust(area_len),
                        f"{sum_total_percent:.1%}".rjust(7),
                        area_fs.format(area_list[1], unit_tag*unit_cnt[1], bk).rjust(area_len),
                        area_fs.format(area_list[2], unit_tag*unit_cnt[2], bk).rjust(area_len),
                        area_fs.format(area_list[3], unit_tag*unit_cnt[3], bk).rjust(area_len),
                        f"{sum_bbox_percent:.1%}".rjust(7)))
            else:
                logic_area = sum_group.comb_area + sum_group.seq_area
                area_list = [sum_group.total_area, logic_area, sum_group.bbox_area]
                unit_cnt = [1] * 3

                if unit_type == 2:
                    for i in range(0, 3):
                        while area_list[i] >= unit_val:
                            area_list[i] /= unit_val
                            unit_cnt[i] += 1

                print("{}{}  {}  {}  {}  {}  {}".format(
                        f"{gid}: ".rjust(group_len+2),
                        f"{sum_group.name}".ljust(path_len-group_len-2),
                        area_fs.format(area_list[0], unit_tag*unit_cnt[0], ['']*2).rjust(area_len),
                        f"{sum_total_percent:.1%}".rjust(7),
                        area_fs.format(area_list[1], unit_tag*unit_cnt[1], bk).rjust(area_len),
                        area_fs.format(area_list[2], unit_tag*unit_cnt[2], bk).rjust(area_len),
                        f"{sum_bbox_percent:.1%}".rjust(7)))

    else:
        show_divider(path_len, area_len, table_attr)

    print()
#}}}

def show_bbox_area(design: Design, table_attr: TableAttr):
    """Scan and show all black-box area"""  #{{{
    top_node = design.top_node
    node_dict = design.node_dict
    max_path_len = max_area = sub_bbox = 0

    ## Backward trace from black-box node

    for node in node_dict.values():
        if node.bbox_area != 0:
            node.is_show = True

            if table_attr.view_type == 'tree':
                path_len = len(node.bname) + node.level * 2
            elif table_attr.view_type == 'inst':
                path_len = len(node.bname)
            else:
                path_len = len(node.dname) + len(node.bname) + 1

            if path_len > max_path_len:
                max_path_len = path_len

            if node.bbox_area > max_area:
                max_area = node.bbox_area

            while True:
                try:
                    node.parent.scans.add(node)
                    if len(node.parent.scans) > 1:
                        break
                    node = node.parent
                except Exception:
                    break

    ## Show area report

    path_len = max_path_len + 5 if table_attr.is_show_level else max_path_len

    if table_attr.view_type == 'path' and not table_attr.is_nosplit:
        path_len = table_attr.path_col_size
    elif max_path_len < table_attr.path_col_size:
        path_len = table_attr.path_col_size

    area_len = int(math.log10(math.ceil(max_area))) + 2 + table_attr.dec_place
    area_len += len(table_attr.unit.tag)

    if table_attr.is_show_ts:
        area_len += int(math.log(max_area) / math.log(1000))
    if area_len < DEFAULT_AREA_COL_SIZE:
        area_len = DEFAULT_AREA_COL_SIZE 

    print()
    show_divider(path_len, area_len, table_attr)
    show_header(path_len, area_len, table_attr)
    show_divider(path_len, area_len, table_attr)

    area_fs = table_attr.area_fs
    unit_tag = table_attr.unit.tag
    unit_val = table_attr.unit.value
    unit_tag = table_attr.unit.tag
    unit_type = table_attr.unit.type

    scan_stack = [top_node]
    sym_list = []

    while len(scan_stack):
        node = scan_stack.pop()
        total_percent = node.bbox_area / top_node.total_area

        if table_attr.view_type == 'tree':
            try:
                if node is top_node:
                    sym = ""

                elif scan_stack[-1].level == node.level:
                    sym = "".join(sym_list + [ISYM]) 

                    if len(node.scans):
                        sym_list.append(BSYM)

                elif scan_stack[-1].level < node.level:
                    sym = "".join(sym_list + [ESYM])

                    if len(node.scans):
                        sym_list.append("  ")
                    else:
                        sym_list = sym_list[:scan_stack[-1].level - node.level]

            except Exception:
                sym = "".join(sym_list + [ESYM])

                if len(node.scans):
                    sym_list.append("  ")

            path_name = "".join((sym, node.bname))

        else:
            if node.level < 2 or table_attr.view_type == 'inst':
                path_name = node.bname
            else:
                path_name = '/'.join((node.dname, node.bname))

        if table_attr.is_show_level:
            path_name = f"({node.level:2d}) " + path_name

        if not node.is_show and table_attr.trace_root == 'leaf':
            pass
        else:
            if len(path_name) > path_len:
                print(f"{path_name.ljust(path_len)}")
                print(f"{' ' * path_len}", end='')
            else:
                print(f"{path_name.ljust(path_len)}", end='')

            sub_bbox += node.bbox_area

            if node.is_show:
                bbox_area = node.bbox_area
                unit_cnt = 1

                if unit_type == 2:
                    while bbox_area >= unit_val:
                        bbox_area /= unit_val
                        unit_cnt += 1

                print("  {}  {}  {}  {}  {}".format(
                        f"-".rjust(area_len),
                        f"{total_percent:.1%}".rjust(7),
                        f"-".rjust(area_len),
                        area_fs.format(bbox_area, unit_tag*unit_cnt, ['']*2).rjust(area_len),
                        f"-".rjust(7)))
            else:
                print("  {}  {}  {}  {}  {}".format(f"-".rjust(area_len),
                                                    f"-".rjust(7),
                                                    f"-".rjust(area_len),
                                                    f"-".rjust(area_len),
                                                    f"-".rjust(7)))

        if table_attr.is_reorder:
            scan_stack.extend(sorted(node.scans, key=lambda x:x.total_area))
        else:
            scan_stack.extend(sorted(node.scans, key=lambda x:x.bname, reverse=True))

    show_divider(path_len, area_len, table_attr)
    print()
#}}}

def show_cmp_area(root_list: list, design_list: list, table_attr: TableAttr):
    """Show hierarchical area for compare mode"""  #{{{

    ## Group sum and remove hide node

    global level_list
    max_path_len = max_area = 0
    max_gid = -1

    design_count = len(design_list)
    sum_list = [copy.deepcopy(sum_dict) for i in range(design_count)]

    for level in range(len(level_list)-1, -1, -1):
        for node in level_list[level]:
            path = '/'.join([node.dname, node.bname]) if node.level > 1 else node.bname
            design_base = design_list[table_attr.base_design]

            if node.gid is not None:
                gid_abs = node.gid if node.gid >= 0 else abs(node.gid+1)

                for idx in range(design_count):
                    try:
                        total_area_s = design_list[idx].node_dict[path].total_area
                    except KeyError:
                        total_area_s = math.nan
                    sum_group_s = sum_list[idx][gid_abs]

                    if node.gid >= 0:
                        sum_group_s.total_area += total_area_s
                    else:
                        sum_group_s.total_area -= total_area_s

                if gid_abs > max_gid:
                    max_gid = gid_abs

            if node.is_hide or not node.is_show:
                if len(node.scans) == 0 and node.parent is not None:
                    node.parent.scans.remove(node)
                else:
                    node.is_show = False
            else:
                if table_attr.view_type == 'tree':
                    path_len = len(node.bname) + node.level * 2
                elif table_attr.view_type == 'inst':
                    path_len = len(node.bname)
                else:
                    path_len = len(node.dname) + len(node.bname) + 1

                if len(tag_dict) != 0 and table_attr.view_type != 'tree':
                    inst_path = node.bname if node.level < 2 else '/'.join((node.dname, node.bname))
                    if inst_path in tag_dict:
                        path_len = len(tag_dict[inst_path])

                if path_len > max_path_len:
                    max_path_len = path_len

                for design in design_list:
                    try:
                        total_area_s = design.node_dict[path].total_area
                        design.diff_dict[path] = total_area_s - design_base.node_dict[path].total_area
                        if table_attr.is_cmp_pr:
                            design.diff_dict[path] /= design_base.node_dict[path].total_area
                    except KeyError:
                        pass

                    if total_area_s > max_area:
                        max_area = total_area_s

                    if table_attr.cmp_type == 2:
                        design_base = design

    ## Show area report

    path_len = max_path_len + 5 if table_attr.is_show_level else max_path_len

    if table_attr.view_type == 'path' and not table_attr.is_nosplit:
        path_len = table_attr.path_col_size
    elif path_len < table_attr.path_col_size:
        path_len = table_attr.path_col_size

    if len(sum_dict):
        for gid, group in sum_dict.items():
            gid_len = 0 if gid == 0 else int(math.log10(gid))
            grp_len = len(group.name) + gid_len + 3
            if path_len < grp_len:
                path_len = grp_len

    if max_area == 0:
        area_len = 0
    else:
        area_len = int(math.log10(math.ceil(max_area))) + 2 + table_attr.dec_place
        area_len += len(table_attr.unit.tag)

    if table_attr.is_show_ts:
        area_len += int(math.log(max_area) / math.log(1000))
    if table_attr.cmp_type != 1:
        area_len += 3

    cmp_type = table_attr.cmp_type
    for name in table_attr.design_name:
        ds_len = len(name) if cmp_type == 1 else len(name) + 2
        if ds_len > area_len:
            area_len = ds_len

    if area_len < DEFAULT_AREA_COL_SIZE:
        area_len = DEFAULT_AREA_COL_SIZE 

    print()
    show_divider(path_len, area_len, table_attr)
    show_header(path_len, area_len, table_attr)
    show_divider(path_len, area_len, table_attr)

    area_fs = table_attr.area_fs
    unit_val = table_attr.unit.value
    unit_tag = table_attr.unit.tag
    unit_type = table_attr.unit.type

    for root_idx, root_node in enumerate(root_list):
        if root_idx > 0:
            print()

        scan_stack = [root_node]
        sym_list = []

        while len(scan_stack):
            node = scan_stack.pop()
            path = '/'.join([node.dname, node.bname]) if node.level > 1 else node.bname

            if table_attr.view_type == 'tree':
                try:
                    if node is root_node:
                        sym = ""
                    elif scan_stack[-1].level < node.level:
                        sym = "".join(sym_list + [ESYM])
                        if len(node.scans):
                            sym_list.append("  ")
                        else:
                            sym_list = sym_list[:scan_stack[-1].level - node.level]
                    else:
                        for idx in range(len(scan_stack)-1, -1, -1):
                            next_node = scan_stack[idx]
                            if next_node.level == node.level and not next_node.is_hide:
                                sym = "".join(sym_list + [ISYM]) 
                                break
                            elif next_node.level < node.level:
                                sym = "".join(sym_list + [ESYM])
                                break
                        else:
                            sym = "".join(sym_list + [ESYM])

                        if len(node.scans):
                            sym_list.append(BSYM)
                except Exception:
                    sym = "".join(sym_list + [ESYM])
                    if len(node.scans):
                        sym_list.append("  ")

                path_name = "".join((sym, node.bname))
            elif node.level < 2 or table_attr.view_type == 'inst':
                path_name = node.bname
            else:
                path_name = '/'.join((node.dname, node.bname))

            if len(tag_dict) != 0 and table_attr.view_type != 'tree':
                inst_path = node.bname if node.level < 2 else '/'.join((node.dname, node.bname))
                if inst_path in tag_dict:
                    path_name = tag_dict[inst_path]

            if table_attr.is_show_level:
                path_name = f"({node.level:2d}) " + path_name

            if node.gid is not None:
                if node.gid >= 0:
                    star = ' *{}+'.format(gid := node.gid)
                else:
                    star = ' *{}-'.format(gid := abs(node.gid+1))

                if gid > max_gid:
                    max_gid = gid
            else:
                star = ''

            if not node.is_show and table_attr.trace_root == 'leaf':
                pass
            else:
                if len(path_name) > path_len:
                    print(f"{path_name.ljust(path_len)}")
                    print(f"{' ' * path_len}", end='')
                else:
                    print(f"{path_name.ljust(path_len)}", end='')

                if node.is_show:
                    for idx in range(design_count):
                        unit_cnt_d = unit_cnt_a = 1
                        try:
                            total_diff = design_list[idx].diff_dict[path]
                            total_area = design_list[idx].node_dict[path].total_area

                            if unit_type == 2:
                                while total_diff >= unit_val:
                                    total_diff /= unit_val
                                    unit_cnt_d += 1
                            
                            if unit_type == 2:
                                while total_area >= unit_val:
                                    total_area /= unit_val
                                    unit_cnt_a += 1

                            bk = ['+', ''] if total_diff >= 0 else ['-', '']
                            unit_tag_g = unit_tag
                        except KeyError:
                            total_area = math.nan
                            total_diff = math.nan
                            bk = [''] * 2
                            unit_tag_g = ''

                        if table_attr.cmp_type == 2 and idx != 0:
                            if table_attr.is_cmp_pr:
                                print("  ({})".format(
                                        f"{bk[0]}{abs(total_diff):.1%}".rjust(area_len-2)), end='')
                            else:
                                print("  ({})".format(
                                        area_fs.format(abs(total_diff), 
                                                       unit_tag_g*unit_cnt_d, bk).rjust(area_len-2)), end='')

                        print("  {}".format(
                                area_fs.format(total_area, unit_tag_g*unit_cnt_a, ['']*2).rjust(area_len)),
                                end='')

                        if table_attr.cmp_type == 3:
                            if table_attr.is_cmp_pr:
                                print("  ({})".format(
                                        f"{bk[0]}{abs(total_diff):.1%}".rjust(area_len-2)), end='')
                            else:
                                print("  ({})".format(
                                        area_fs.format(abs(total_diff), 
                                                       unit_tag_g*unit_cnt_d, bk).rjust(area_len-2)), end='')
                    print(f" {star}")
                else:
                    for i in design_count:
                        print("  {}".format(f"-".rjust(area_len)), end='')
                    print()

            if table_attr.is_reorder:
                scan_stack.extend(sorted(node.scans, key=lambda x:x.total_area))
            else:
                scan_stack.extend(sorted(node.scans, key=lambda x:x.bname, reverse=True))

    if len(sum_dict) != 0:
        print()
        show_divider(path_len, area_len, table_attr)
        show_header(path_len, area_len, table_attr, title='Group')
        show_divider(path_len, area_len, table_attr)

        sum_base = sum_list[table_attr.base_design]
        for sum_design in sum_list:
            for gid, sum_grp_s in sum_design.items():
                sum_grp_s.diff_area = sum_grp_s.total_area - sum_base[gid].total_area
                if table_attr.is_cmp_pr:
                    sum_grp_s.diff_area /= sum_base[gid].total_area
            if table_attr.cmp_type == 2:
                sum_base = sum_design

        group_len = 1 if max_gid <= 0 else int(math.log10(max_gid)) + 1

        for gid, sum_group in sorted(sum_dict.items()):
            print("{}{}".format(
                    f"{gid}: ".rjust(group_len+2),
                    f"{sum_group.name}".ljust(path_len-group_len-2)), end='')

            # for sum_dict_s in sum_list:
            for idx in range(design_count):
                total_diff = sum_list[idx][gid].diff_area
                total_area = sum_list[idx][gid].total_area
                unit_cnt_d = unit_cnt_a = 1

                if unit_type == 2:
                    while total_diff >= unit_val:
                        total_diff /= unit_val
                        unit_cnt_d += 1

                if unit_type == 2:
                    while total_area >= unit_val:
                        total_area /= unit_val
                        unit_cnt_a += 1

                if math.isnan(total_area):
                    bk = [''] * 2
                    unit_tag_g = ''
                else:
                    bk = ['+', ''] if total_diff >= 0 else ['-', '']
                    unit_tag_g = unit_tag

                if table_attr.cmp_type == 2 and idx != 0:
                    if table_attr.is_cmp_pr:
                        print("  ({})".format(
                                f"{bk[0]}{abs(total_diff):.1%}".rjust(area_len-2)), end='')
                    else:
                        print("  ({})".format(
                                area_fs.format(abs(total_diff), 
                                               unit_tag_g*unit_cnt_d, bk).rjust(area_len-2)), end='')

                print("  {}".format(
                        area_fs.format(total_area, unit_tag_g*unit_cnt_a, ['']*2).rjust(area_len)), end='')

                if table_attr.cmp_type == 3:
                    if table_attr.is_cmp_pr:
                        print("  ({})".format(
                                f"{bk[0]}{abs(total_diff):.1%}".rjust(area_len-2)), end='')
                    else:
                        print("  ({})".format(
                                area_fs.format(abs(total_diff), 
                                               unit_tag_g*unit_cnt_d, bk).rjust(area_len-2)), end='')
            print()
    else:
        show_divider(path_len, area_len, table_attr)

    print()
#}}}

def show_header(path_len: int, area_len: int, table_attr: TableAttr, title: str='Instance'):
    """Show header"""  #{{{

    print("{}  ".format(title.ljust(path_len)), end='')

    if table_attr.cmp_type == 1:
        for name in table_attr.design_name:
            print("{}  ".format(name.ljust(area_len)), end='')
        print()
    elif table_attr.cmp_type == 2:
        design_count = len(table_attr.design_name)
        print("{}  ".format(table_attr.design_name[0].ljust(area_len)), end='')
        for idx in range(1, design_count):
            print("{}  ".format(table_attr.design_name[idx].ljust(area_len)), end='')
            print("{}  ".format(table_attr.design_name[idx].ljust(area_len)), end='')
        print()

        print("{}  ".format(''.ljust(path_len)), end='')
        for idx in range(0, design_count-1):
            name = '- ' + table_attr.design_name[idx]
            print("{}  ".format(''.ljust(area_len)), end='')
            print("{}  ".format(name.ljust(area_len)), end='')
        print("{}  ".format(''.ljust(area_len)))
    elif table_attr.cmp_type == 3:
        design_count = len(table_attr.design_name)
        for idx in range(design_count):
            print("{}  ".format(table_attr.design_name[idx].ljust(area_len)), end='')
            print("{}  ".format(table_attr.design_name[idx].ljust(area_len)), end='')
        print()

        print("{}  ".format(''.ljust(path_len)), end='')
        for idx in range(design_count):
            name = '- ' + table_attr.design_name[table_attr.base_design]
            print("{}  ".format(''.ljust(area_len)), end='')
            print("{}  ".format(name.ljust(area_len)), end='')
        print()
    else:
        print("{}  ".format('Absolute'.ljust(area_len)), end='')

        if table_attr.is_brief:
            print("{}".format('Percent'.ljust(7)))
        else:
            print("{}  ".format('Percent'.ljust(7)), end='')
            if table_attr.is_logic_sep:
                print("{}  ".format('Combi-'.ljust(area_len)), end='')
                print("{}  ".format('Noncombi-'.ljust(area_len)), end='')
            else:
                print("{}  ".format('Logic'.ljust(area_len)), end='')
            print("{}  ".format('Black-'.ljust(area_len)), end='')
            print("{}".format('Percent'.ljust(7)))

        print("{}  ".format(''.ljust(path_len)), end='')
        print("{}  ".format('Total'.ljust(area_len)), end='')

        if table_attr.is_brief:
            print("{}".format('Total'.ljust(7)))
        else:
            print("{}  ".format('Total'.ljust(7)), end='')
            if table_attr.is_logic_sep:
                print("{}  ".format('national'.ljust(area_len)), end='')
                print("{}  ".format('national'.ljust(area_len)), end='')
            else:
                print("{}  ".format('Area'.ljust(area_len)), end='')
            print("{}  ".format('Boxes'.ljust(area_len)), end='')
            print("{}  ".format('BBox'.ljust(7)))
#}}}

def show_divider(path_len: int, area_len: int, table_attr: TableAttr):
    """Show header"""  #{{{

    print("{}  ".format('-' * path_len), end='')

    if table_attr.cmp_type != 0:
        if table_attr.cmp_type == 1:
            design_count = len(table_attr.design_name)
        elif table_attr.cmp_type == 2:
            design_count = len(table_attr.design_name) * 2 - 1
        else:
            design_count = len(table_attr.design_name) * 2

        for i in range(design_count):
            print("{}  ".format('-' * area_len), end='')
        print()
    else:
        print("{}  ".format('-' * area_len), end='')
        if table_attr.is_brief:
            print("{}".format('-' * 7))
        else:
            print("{}  ".format('-' * 7), end='')
            if table_attr.is_logic_sep:
                print("{}  ".format('-' * area_len), end='')
            print("{}  ".format('-' * area_len), end='')
            print("{}  ".format('-' * area_len), end='')
            print("{}".format('-' * 7))
#}}}

### Main Function ###

def create_argparse() -> argparse.ArgumentParser:
    """Create Argument Parser"""  #{{{
    parser = argparse.ArgumentParser(
                formatter_class=argparse.RawTextHelpFormatter,
                description="Design compiler area report analysis.")

    subparsers = parser.add_subparsers(dest='proc_mode', required=True, help="select one of process modes.")

    parser.add_argument('-version', action='version', version=VERSION)
    parser.add_argument('-dump', dest='dump_fn', metavar='<file>', 
                                    help="dump leaf nodes in the list\n ")

    parser.add_argument('-ra', dest='ratio', metavar='<float>', type=float, default=1.0, 
                                    help="convert ratio")

    unit_gparser = parser.add_mutually_exclusive_group()
    unit_gparser.add_argument('-u1', dest='unit1', metavar='unit', 
                                    choices=['k', 'K', 'w', 'W', 'm', 'M', 'b', 'B'],
                                    help="unit change (choices: [kKwWmMbB])") 
    unit_gparser.add_argument('-u2', dest='unit2', metavar='unit', 
                                    choices=['k', 'K', 'w', 'W', 'm', 'M', 'b', 'B'],
                                    help="scientific notation (choices: [kKwWmMbB])\n ") 

    parser.add_argument('-dp', dest='dec_place', metavar='<int>', type=int, default=4, 
                                    help="number of decimal places of area")
    parser.add_argument('-ts', dest='is_show_ts', action='store_true', 
                                    help="show thousands separators")

    area_gparser = parser.add_mutually_exclusive_group()
    area_gparser.add_argument('-br', dest='is_brief', action='store_true', 
                                    help="only show total area/percent value")
    area_gparser.add_argument('-ls', dest='is_logic_sep', action='store_true', 
                                    help="show combi/non-combi area separately")

    parser.add_argument('-ro', dest='is_reorder', action='store_true', 
                                    help="area reorder (large first)")

    parser.add_argument('-lv', dest='is_show_level', action='store_true', 
                                    help="show hierarchical level")
    parser.add_argument('-ns', dest='is_nosplit', action='store_true', 
                                    help="cell path no-split\n ")

    path_gparser = parser.add_mutually_exclusive_group()
    path_gparser.add_argument('-t', dest='is_tree_view', action='store_true', 
                                    help="show path with tree view")
    path_gparser.add_argument('-i', dest='is_inst_view', action='store_true', 
                                    help="only show instance name (instance view)")

    # create the parser for normal mode
    parser_norm = subparsers.add_parser('norm', help='normal mode')
    parser_norm.add_argument('rpt_fn', help="area report path") 

    # create the parser for advance mode
    parser_adv = subparsers.add_parser('adv', help='advance mode')
    parser_adv.add_argument('cfg_fn', help="configuration file") 
    parser_adv.add_argument('rpt_fn', help="area report path") 

    parser_adv.add_argument('-tr', dest='trace_root', metavar='<type>', choices=['top', 'com', 'sub'],
                                    help="""backward trace root [top|com|sub]""")
    parser_adv.add_argument('-v', dest='is_verbose', action='store_true',
                                    help="show area of all trace nodes")

    # create the parser for compare mode
    parser_cmp = subparsers.add_parser('cmp', help='compare mode')
    parser_cmp.add_argument('cfg_fn', help="configuration file") 
    parser_cmp.add_argument('rpt_fn', nargs='+', help="area report path") 

    parser_cmp.add_argument('-pr', dest='is_cmp_pr', action='store_true',
                                    help="show difference percent")
    parser_cmp.add_argument('-db', dest='diff_base', metavar='<id>', type=int, default=0,
                                    help="""difference base id (default:0)""")
    parser_cmp.add_argument('-v', dest='is_verbose', action='store_true',
                                    help="show area of all trace nodes")

    cmp_tparser = parser_cmp.add_mutually_exclusive_group(required=True)

    cmp_tparser.add_argument('-t1', dest='is_cmp_t1', action='store_true',
                                    help="type1: only show areas ------------- \
                                            (A0 A1 A2 ...)")
    cmp_tparser.add_argument('-t2', dest='is_cmp_t2', action='store_true',
                                    help="type2: areas and diff with left ---- \
                                            (A0(---) A1(D01) A2(D12) ...)")
    cmp_tparser.add_argument('-t3', dest='is_cmp_t3', action='store_true',
                                    help="type2: areas and diff with select -- \
                                            (A0(DS0) A1(DS1) A2(DS2) ...)")

    # create the parser for black-box scan mode
    parser_bbox = subparsers.add_parser('bbox', help='black-box scan mode')
    parser_bbox.add_argument('rpt_fn', help="area report path") 

    return parser
#}}}

def main():
    """Main Function"""  #{{{

    parser = create_argparse()
    args = parser.parse_args()

    unit = UnitAttr()
    if args.unit1 is not None:
        unit.tag = args.unit1
        unit.type = 1
    elif args.unit2 is not None:
        unit.tag = args.unit2
        unit.type = 2

    match unit.tag.lower():
        case 'k':
            unit.value = pow(10, 3)
            unit_info = "1 thousand"
        case 'w':
            unit.value = pow(10, 4)
            unit_info = "10 thousand"
        case 'm':
            unit.value = pow(10, 6)
            unit_info = "1 million"
        case 'b':
            unit.value = pow(10, 9)
            unit_info = "1 billion"
        case _:
            unit_info = "1"

    if args.proc_mode == 'adv' and args.trace_root is not None:
        trace_root = args.trace_root
    else:
        trace_root = 'top' if args.is_tree_view else 'leaf'

    if args.is_show_ts:
        area_fs = "{2[0]}{0:,." + str(args.dec_place) + "f}{1}{2[1]}"
    else:
        area_fs = "{2[0]}{0:." + str(args.dec_place) + "f}{1}{2[1]}"

    table_attr = TableAttr(
                    area_fs=area_fs,
                    ratio=args.ratio,
                    unit=unit,
                    dec_place=args.dec_place,
                    is_show_ts=args.is_show_ts,
                    is_brief=args.is_brief,
                    is_logic_sep=args.is_logic_sep,
                    is_reorder=args.is_reorder,
                    is_show_level=args.is_show_level,
                    is_nosplit=args.is_nosplit,
                    view_type=('tree' if args.is_tree_view else 'inst' if args.is_inst_view else 'path'),
                    trace_root=trace_root)

    if args.proc_mode == 'norm':
        table_attr.is_verbose = True
    elif args.proc_mode == 'adv':
        table_attr.is_verbose = args.is_verbose
    elif args.proc_mode == 'cmp':
        table_attr.is_verbose = args.is_verbose
        table_attr.is_cmp_pr = args.is_cmp_pr
        table_attr.base_design = args.diff_base
        if args.is_cmp_t1:
            table_attr.cmp_type = 1
        elif args.is_cmp_t2:
            table_attr.cmp_type = 2
        elif args.is_cmp_t3:
            table_attr.cmp_type = 3

    ## Main process

    global root_list

    load_area(args.rpt_fn, args.proc_mode, table_attr)
    design = design_list[table_attr.base_design]

    if args.proc_mode == 'cmp':
        print()
        print("=" * 32)
        print(f" Total Area Compare ".center(32, '='))
        print("=" * 32)
    else:
        area_t = design.total_area
        area_b = design.bbox_area
        area_l = area_t - area_b

        percent_l = area_l / area_t
        percent_b = area_b / area_t

        area_len = int(math.log10(math.ceil(area_t))) + 2 + table_attr.dec_place
        area_len += len(table_attr.unit.tag)
        if table_attr.is_show_ts:
            area_len += int(math.log(area_t) / math.log(1000))

        area_list = [area_t, area_l, area_b]
        unit_val = table_attr.unit.value
        unit_tag = table_attr.unit.tag
        unit_cnt = [1 if table_attr.unit.type != 0 else 0] * 3

        if table_attr.unit.type == 2:
            for i in range(0, 3):
                while area_list[i] >= unit_val:
                    area_list[i] /= unit_val 
                    unit_cnt[i] += 1

        area_fs = "{:." + str(table_attr.dec_place) + "f}{}"
        area_str_t = area_fs.format(area_list[0], unit_tag * unit_cnt[0]).rjust(area_len)
        area_str_l = area_fs.format(area_list[1], unit_tag * unit_cnt[1]).rjust(area_len)
        area_str_b = area_fs.format(area_list[2], unit_tag * unit_cnt[2]).rjust(area_len)

        print()
        print(f" Top Summary ".center(32, '='))
        print("  total: {} ({:>6.1%})".format(area_str_t, 1.0))
        print("  logic: {} ({:>6.1%})".format(area_str_l, percent_l))
        print("   bbox: {} ({:>6.1%})".format(area_str_b, percent_b))
        print("=" * 32)

    print(f"\nratio: {str(table_attr.ratio)}  unit: {unit_info}")

    if args.proc_mode == 'norm':
        show_hier_area([design.top_node], design, table_attr)
    elif args.proc_mode == 'bbox':
        table_attr.is_logic_sep = False
        show_bbox_area(design, table_attr)
    else:
        load_cfg(args.cfg_fn, design, table_attr)

        if table_attr.is_sub_sum:
            print("\n() : Sub-module Area Summation")

        if table_attr.trace_root == 'sub':
            if args.proc_mode == 'adv':
                show_hier_area(root_list, design, table_attr)
            else:
                show_cmp_area(root_list, design_list, table_attr)
        else:
            root_node = design.top_node
            if table_attr.trace_root == 'com':
                while True:
                    if root_node.is_show:
                        break
                    if len(root_node.scans) > 1:
                        break
                    root_node = tuple(root_node.scans)[0]

            if args.proc_mode == 'adv':
                show_hier_area([root_node], design, table_attr)
            else:
                show_cmp_area([root_node], design_list, table_attr)

    if args.dump_fn is not None:
        with open(args.dump_fn, 'w') as f:
            scan_stack = [design.top_node]
            while len(scan_stack):
                node = scan_stack.pop()
                if len(node.scans) == 0:
                    path_name = "" if node.level < 2 else f"{node.dname}/"
                    path_name += node.bname
                    f.write(f"{path_name}\n")
                else:
                    scan_stack.extend(node.scans)
#}}}

if __name__ == '__main__':
    main()
