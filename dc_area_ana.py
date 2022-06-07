#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-only
#
# Design Compiler Area Report Analysis
#
# Copyright (C) 2022 Yeh, Hsin-Hsien <yhh76227@gmail.com>
#
import argparse
import gzip
import math
import os
import re
import sys
import textwrap
from dataclasses import dataclass

### Global Parameter ###  

DEFAULT_PATH_COL_SIZE = 32
DEFAULT_AREA_COL_SIZE = 9
ISYM = f"{0x251c:c}{0x2500:c}"
ESYM = f"{0x2514:c}{0x2500:c}"
BSYM = f"{0x2502:c} "

top_node = None
node_dict = {}
scan_set = set()
level_list = []
sum_dict = {}

### Class Defintion ###

class Node:
    def __init__(self, dname, bname, level, total_area, bbox_area, 
                 parent=None, childs=None, scans=None):
    #{{{
        self.dname = dname
        self.bname = bname
        self.level = level
        self.total_area = total_area
        self.bbox_area = bbox_area
        self.parent = parent
        self.childs = set() if childs is None else childs
        self.scans = set() if scans is None else scans
        self.is_dominant = False
        self.is_hide = False
        self.group_id = None
        self.sub_bbox_area = -1
    #}}}

@dataclass
class TableAttribute:
#{{{
    is_show_level: bool = False
    is_tree_view: bool = False
    is_bname_view: bool = False
    is_ext_pathcol: bool = False
    is_trace_bbox: bool = False
    is_full_trace: bool = False
    path_col_size: int = DEFAULT_PATH_COL_SIZE
#}}}

@dataclass
class SumGroup:
#{{{
    name: str
    total_area: int = 0
    logic_area: int = 0
    bbox_area: int = 0
#}}}

### Sub Function ###

def load_area(area_fp, is_full_dominant: bool, table_attr: TableAttribute) -> int:  
    """Load area report"""  #{{{
    ## return: total_bbox_area
    global top_node
    global node_dict
    fsm = max_path_len = total_bbox_area = 0

    with open(area_fp) as f:
        line = f.readline()
        while line:
            if fsm == 2 and len(toks:=line.split()):
                if toks[0].startswith("---"):
                    table_attr.path_col_size = max_path_len 
                    return total_bbox_area

                path = toks[0]
                del toks[0]

                names = path.split('/')
                dname = '/'.join(names[:-1])  # dirname
                bname = names[-1]             # basename

                if len(toks) == 0:  # total area
                    line = f.readline()
                    toks = line.split()
                total_area = float(toks[0])
                del toks[0]

                for i in range(3):
                    if len(toks) == 0:
                        line = f.readline()
                        toks = line.split()
                    del toks[0]

                if len(toks) == 0:  # bbox area
                    line = f.readline()
                    toks = line.split()
                bbox_area = float(toks[0])
                del toks[0]

                total_bbox_area += bbox_area

                if not top_node:
                    top_node = node = Node(dname, bname, 0, total_area, bbox_area)
                elif len(names) == 1:
                    node = Node(dname, bname, 1, total_area, bbox_area, parent=top_node)
                    top_node.childs.add(node)
                else:
                    parent_node = node_dict[dname]
                    node = Node(dname, bname, len(names), total_area, bbox_area, parent=parent_node)
                    parent_node.childs.add(node)

                node_dict[path] = node

                if is_full_dominant:
                    node.is_dominant = True
                    node.scans = node.childs

                if table_attr.is_tree_view:
                    path_len = len(node.bname) + node.level * 2
                elif table_attr.is_bname_view:
                    path_len = len(node.bname)
                elif table_attr.is_ext_pathcol:
                    path_len = len(node.dname) + len(node.bname) + 1
                else:
                    path_len = DEFAULT_PATH_COL_SIZE

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

def load_cfg(cfg_fp, is_full_dominant: bool, table_attr: TableAttribute):
    """Load configuration"""  #{{{
    global node_dict
    global scan_set
    global level_list
    max_path_len = 0
    max_lv = -1

    with open(cfg_fp) as f:
        line_no = 0
        for line in f.readlines():
            line_no += 1
            toks = line.split()
            if len(toks):
                if toks[0][0] == '#':
                    continue

                if toks[0].startswith('grp'):
                    group, name = line.split(':')
                    group_id = 0 if group.strip() == 'grp' else int(group.strip()[3:])
                    name = name.strip('\"\'\n ')
                    if group_id not in sum_dict:
                        sum_dict[group_id] = SumGroup(name)
                    else:
                        sum_dict[group_id].name = name
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
                    node_list.append(node_dict[toks[0]])
                    cmd_list.extend(toks[1:])

                for node in node_list:
                    try:
                        node.is_dominant = True

                        if table_attr.is_tree_view:
                            path_len = len(node.bname) + node.level * 2
                        elif table_attr.is_bname_view:
                            path_len = len(node.bname)
                        elif table_attr.is_ext_pathcol:
                            path_len = len(node.dname) + len(node.bname) + 1
                        else:
                            path_len = DEFAULT_PATH_COL_SIZE

                        if path_len > max_path_len:
                            max_path_len = path_len

                        if max_lv < node.level:
                            level_list.extend([set() for i in range(node.level - max_lv)])
                            max_lv = node.level

                        scan_set.add(node)
                        level_list[node.level].add(node)
                    except Exception as e:
                        print("-" * 60)
                        print("ConfigParseError: (line: {})".format(line_no))
                        print("unexisted path in the list.")
                        print("-" * 60)
                        raise e

                    ## Load command from configuration

                    try:
                        sub_max_path_len, sub_max_lv = parse_cmd(node, cmd_list, table_attr)
                    except Exception as e:
                        print("-" * 60)
                        print("ConfigParseError: (line: {})".format(line_no))
                        print("error command.")
                        print("-" * 60)
                        raise e

                    if sub_max_path_len > max_path_len:
                        max_path_len = sub_max_path_len
                    if sub_max_lv > max_lv:
                        max_lv = sub_max_lv

    ## Backward scan link

    for level in range(max_lv, 0, -1):
        for node in level_list[level]:
            if node.parent:
                if is_full_dominant:
                    node.parent.is_dominant = True

                    if table_attr.is_tree_view:
                        path_len = len(node.bname) + node.level * 2
                    elif table_attr.is_bname_view:
                        path_len = len(node.bname)
                    elif table_attr.is_ext_pathcol:
                        path_len = len(node.dname) + len(node.bname) + 1
                    else:
                        path_len = DEFAULT_PATH_COL_SIZE

                    if path_len > max_path_len:
                        max_path_len = path_len

                node.parent.scans.add(node)
                level_list[level-1].add(node.parent)

    table_attr.path_col_size = max_path_len
#}}}

def parse_cmd(node: Node, cmd_list: list, table_attr: TableAttribute) -> (int, int):
    """Parsing command"""  #{{{
    ## return: max_path_len, max_lv
    global sum_dict
    idx = max_path_len = max_lv = 0
    end_cond = len(cmd_list)

    while idx < end_cond:
        cmd = cmd_list[idx]
        idx += 1

        if cmd == '':
            continue
        if cmd[0] == '#':
            break

        if cmd.startswith('add') or cmd.startswith('sub') :
            sum_toks = cmd.split(':')
            group_id = 0 if len(sum_toks[0]) == 3 else int(sum_toks[0][3:])
            node.group_id = group_id if sum_toks[0][0:3] == 'add' else -group_id - 1
            if group_id not in sum_dict:
                sum_dict[group_id] = SumGroup(f'Group {group_id}')
            if len(sum_toks) > 1:
                name = sum_toks[1]
                if name.startswith('\"'):
                    while not name.endswith('\"'):
                        name += f" {cmd_list[idx]}"
                        idx += 1
                elif name.startswith('\''):
                    while not name.endswith('\''):
                        name += f" {cmd_list[idx]}"
                        idx += 1
                sum_dict[group_id].name = name.strip('\"\'\n ')
        elif cmd == 'bbox':
            trace_sub_bbox(node)
            table_attr.is_trace_bbox = True
        elif cmd == 'hide':
            node.is_hide = True
        elif cmd == 'inf':
            max_path_len, max_lv = trace_sub_node(node, 'inf', table_attr)
        elif cmd[0] == 'l':
            max_path_len, max_lv = trace_sub_node(node, cmd[1:], table_attr)
        else:
            raise SyntaxError('error command')

    return max_path_len, max_lv
#}}}

def trace_sub_node(cur_node: Node, trace_lv: str, table_attr: TableAttribute) -> (int, int):
    """Trace sub nodes"""  #{{{
    global scan_set
    global level_list
    scan_lv = math.inf if trace_lv == 'inf' else cur_node.level + int(trace_lv)
    max_path_len = 0
    max_lv = len(level_list) - 1

    scan_stack = [cur_node]

    while len(scan_stack):
        node = scan_stack.pop()
        node.is_dominant = True

        if table_attr.is_tree_view:
            path_len = len(node.bname) + node.level * 2
        elif table_attr.is_bname_view:
            path_len = len(node.bname)
        elif table_attr.is_ext_pathcol:
            path_len = len(node.dname) + len(node.bname) + 1
        else:
            path_len = DEFAULT_PATH_COL_SIZE

        if path_len > max_path_len:
            max_path_len = path_len
        
        if max_lv < node.level:
            level_list.extend([set() for i in range(node.level - max_lv)])
            max_lv = node.level

        scan_set.add(node)
        level_list[node.level].add(node)

        if node.level < scan_lv:
            node.scans = node.childs
            scan_stack.extend(node.childs)

    return max_path_len, max_lv
#}}}

def trace_sub_bbox(cur_node: Node):
    """Trace sub black-box area"""  #{{{
    sub_bbox_area = 0
    scan_stack = [cur_node]

    while len(scan_stack):
        node = scan_stack.pop()
        sub_bbox_area += node.bbox_area
        scan_stack.extend(node.childs)

    cur_node.sub_bbox_area = sub_bbox_area
#}}}

def show_hier_area(root_node: Node, table_attr: TableAttribute):
    """Show area with hierarchical view"""  #{{{
    if table_attr.is_show_level:
        path_len = table_attr.path_col_size + 5
    else:
        path_len = table_attr.path_col_size

    if path_len < DEFAULT_PATH_COL_SIZE:
        path_len = DEFAULT_PATH_COL_SIZE

    area_len = int(math.log10(math.ceil(root_node.total_area))) + 6
    if area_len < DEFAULT_AREA_COL_SIZE:
        area_len = DEFAULT_AREA_COL_SIZE 
    if table_attr.is_trace_bbox:
        area_len += 2

    print()
    show_divider(path_len, area_len)
    show_header(path_len, area_len)
    show_divider(path_len, area_len)

    max_group_id = -1
    scan_stack = [root_node]
    sym_list = []

    while len(scan_stack):
        node = scan_stack.pop()
        if node.sub_bbox_area != -1:
            node_area = node.total_area
            node_bbox = node.sub_bbox_area
        else:
            node_area = node.total_area - sum((x.total_area for x in node.childs));
            node_bbox = node.bbox_area

        node_logic = node_area - node_bbox
        total_percent = node.total_area / root_node.total_area

        try:
            bbox_percent = node_bbox / node_area
        except ZeroDivisionError as e:
            if node_bbox == 0:
                bbox_percent = 0
            else:
                raise e

        if table_attr.is_tree_view:
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

        else:
            if node.level < 2 or table_attr.is_bname_view:
                path_name = node.bname
            else:
                path_name = '/'.join((node.dname, node.bname))

        if table_attr.is_show_level:
            path_name = f"({node.level:2d}) " + path_name

        if node.group_id is not None:
            if node.group_id >= 0:
                star = ' *{}+'.format(group_id := node.group_id)
                sum_group = sum_dict[group_id]
                sum_group.total_area += node.total_area
                sum_group.logic_area += node_logic
                sum_group.bbox_area += node_bbox
            else:
                star = ' *{}-'.format(group_id := abs(node.group_id+1))
                sum_group = sum_dict[group_id]
                sum_group.total_area -= node.total_area
                sum_group.logic_area -= node_logic
                sum_group.bbox_area -= node_bbox

            if group_id > max_group_id:
                max_group_id = group_id
        else:
            star = ''

        if not node.is_dominant and not table_attr.is_full_trace:
            pass
        elif node.is_hide and not table_attr.is_full_trace:
            pass
        elif node.is_hide and table_attr.is_full_trace and len(node.scans) == 0:
            pass
        else:
            if len(path_name) > path_len:
                print(f"{path_name.ljust(path_len)}")
                print(f"{' ' * path_len}", end='')
            else:
                print(f"{path_name.ljust(path_len)}", end='')

            # if node.group_id is not None:
            #     if node.group_id >= 0:
            #         star = ' *{}+'.format(group_id := node.group_id)
            #         sum_group = sum_dict[group_id]
            #         sum_group.total_area += node.total_area
            #         sum_group.logic_area += node_logic
            #         sum_group.bbox_area += node_bbox
            #     else:
            #         star = ' *{}-'.format(group_id := abs(node.group_id+1))
            #         sum_group = sum_dict[group_id]
            #         sum_group.total_area -= node.total_area
            #         sum_group.logic_area -= node_logic
            #         sum_group.bbox_area -= node_bbox

            #     if group_id > max_group_id:
            #         max_group_id = group_id
            # else:
            #     star = ''

            if node.sub_bbox_area != -1:
                lbk = '('
                rbk = ')'
                rbk2 = ' '
            elif table_attr.is_trace_bbox:
                lbk = rbk = rbk2 = ' '
            else:
                lbk = rbk = rbk2 = ''

            if node.is_dominant and not node.is_hide:
                print("  {}  {}  {}  {}  {} {}".format(f"{node.total_area:.4f}".rjust(area_len),
                                                       f"{total_percent:.1%}".rjust(7),
                                                       f"{lbk}{node_logic:.4f}{rbk}".rjust(area_len),
                                                       f"{lbk}{node_bbox:.4f}{rbk}".rjust(area_len),
                                                       f"{bbox_percent:.1%}".rjust(7),
                                                       star))
            else:
                print("  {}  {}  {}  {}  {}".format(f"-".rjust(area_len),
                                                    f"-".rjust(7),
                                                    f"-{rbk2}".rjust(area_len),
                                                    f"-{rbk2}".rjust(area_len),
                                                    f"-".rjust(7)))

        scan_stack.extend(sorted(node.scans, key=lambda x:x.total_area))

    if len(sum_dict) != 0:
        print()
        show_divider(path_len, area_len)
        show_header(path_len, area_len, title='Group')
        show_divider(path_len, area_len)

        group_len = 1 if max_group_id == 0 else int(math.log10(max_group_id)) + 1
        bk = ' ' if table_attr.is_trace_bbox else ''
        for group_id, sum_group in sorted(sum_dict.items()):
            sum_bbox_percent = 0 if sum_group.total_area == 0 else sum_group.bbox_area / sum_group.total_area
            sum_total_percent = sum_group.total_area / root_node.total_area
            print("{}{}  {}  {}  {}  {}  {}".format(f"{group_id}: ".rjust(group_len+2),
                                                    f"{sum_group.name}".ljust(path_len-group_len-2),
                                                    f"{sum_group.total_area:.4f}".rjust(area_len),
                                                    f"{sum_total_percent:.1%}".rjust(7),
                                                    f"{bk}{sum_group.logic_area:.4f}{bk}".rjust(area_len),
                                                    f"{bk}{sum_group.bbox_area:.4f}{bk}".rjust(area_len),
                                                    f"{sum_bbox_percent:.1%}".rjust(7)))
    else:
        show_divider(path_len, area_len)

    print()
#}}}

def show_bbox_area(root_node: Node, table_attr: TableAttribute):
    """Scan and show all black-box area"""  #{{{
    global node_dict
    sub_bbox = 0

    if table_attr.is_show_level:
        path_len = table_attr.path_col_size + 5
    else:
        path_len = table_attr.path_col_size

    if path_len < DEFAULT_PATH_COL_SIZE:
        path_len = DEFAULT_PATH_COL_SIZE

    area_len = int(math.log10(math.ceil(root_node.total_area))) + 6
    if area_len < DEFAULT_AREA_COL_SIZE:
        area_len = DEFAULT_AREA_COL_SIZE 

    ## Backward trace from black-box node

    for node in node_dict.values():
        if node.bbox_area != 0:
            node.is_dominant = True
            while True:
                try:
                    node.parent.scans.add(node)
                    if len(node.parent.scans) > 1:
                        break
                    node = node.parent
                except Exception:
                    break

    ## Show area

    print()
    show_divider(path_len, area_len)
    show_header(path_len, area_len)
    show_divider(path_len, area_len)

    scan_stack = [root_node]
    sym_list = []

    while len(scan_stack):
        node = scan_stack.pop()
        total_percent = node.bbox_area / root_node.total_area

        if table_attr.is_tree_view:
            try:
                if node is root_node:
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
            if node.level < 2 or table_attr.is_bname_view:
                path_name = node.bname
            else:
                path_name = '/'.join((node.dname, node.bname))

        if table_attr.is_show_level:
            path_name = f"({node.level:2d}) " + path_name

        if not node.is_dominant and not table_attr.is_full_trace:
            pass
        else:
            if len(path_name) > path_len:
                print(f"{path_name.ljust(path_len)}")
                print(f"{' ' * path_len}", end='')
            else:
                print(f"{path_name.ljust(path_len)}", end='')

            sub_bbox += node.bbox_area

            if node.is_dominant:
                print("  {}  {}  {}  {}  {}".format(f"-".rjust(area_len),
                                                    f"{total_percent:.1%}".rjust(7),
                                                    f"-".rjust(area_len),
                                                    f"{node.bbox_area:.4f}".rjust(area_len),
                                                    f"-".rjust(7)))
            else:
                print("  {}  {}  {}  {}  {}".format(f"-".rjust(area_len),
                                                    f"-".rjust(7),
                                                    f"-".rjust(area_len),
                                                    f"-".rjust(area_len),
                                                    f"-".rjust(7)))

        scan_stack.extend(sorted(node.scans, key=lambda x:x.total_area))

    show_divider(path_len, area_len)

    if sub_bbox != 0:
        sub_total_percent = sub_bbox / root_node.total_area
        print("{}  {}  {}  {}  {}  {}".format(f"Black-box Total".ljust(path_len),
                                              f"-".rjust(area_len),
                                              f"{sub_total_percent:.1%}".rjust(7),
                                              f"-".rjust(area_len),
                                              f"{sub_bbox:.4f}".rjust(area_len),
                                              f"-".rjust(7)))

    print()
#}}}

def show_header(path_len: int, area_len: int, title: str='Instance'):
    """Show header"""  #{{{
    print("{}  {}  {}  {}  {}  {}".format(title.ljust(path_len),
                                          'Absolute'.ljust(area_len),
                                          'Percent'.ljust(7),
                                          'Logic'.ljust(area_len),
                                          'Black-'.ljust(area_len),
                                          'Percent'.ljust(7)))

    print("{}  {}  {}  {}  {}  {}".format(''.ljust(path_len),
                                          'Total'.ljust(area_len),
                                          'Total'.ljust(7),
                                          'Area'.ljust(area_len),
                                          'Boxes'.ljust(area_len),
                                          'BBox'.ljust(7)))
#}}}

def show_divider(path_len: int, area_len: int):
    """Show header"""  #{{{
    print("{}  {}  {}  {}  {}  {}".format('-' * path_len,
                                          '-' * area_len,
                                          '-' * 7,
                                          '-' * area_len,
                                          '-' * area_len,
                                          '-' * 7))
#}}}

### Main Function ###

def main():
    """Main Function"""  #{{{
    parser = argparse.ArgumentParser(
                formatter_class=argparse.RawTextHelpFormatter,
                description="Design compiler area report analysis.")

    subparsers = parser.add_subparsers(dest='proc_mode', help="Select one of process modes.")

    parser.add_argument('--dump', dest='dump_fn', metavar='<file>', help="dump the list of leaf nodes")
    parser.add_argument('-l', dest='is_show_level', action='store_true', help="show hierarchical level")

    path_gparser = parser.add_mutually_exclusive_group()
    path_gparser.add_argument('-t', dest='is_tree_view', action='store_true', 
                                    help="show path with tree view")
    path_gparser.add_argument('-i', dest='is_bname_view', action='store_true', 
                                    help="only show instance name (basename view)")
    path_gparser.add_argument('-f', dest='is_ext_pathcol', action='store_true', 
                                    help="extend path column length to full path size (for full path view)")

    # create the parser for normal mode
    parser_norm = subparsers.add_parser('norm', help='normal mode')
    parser_norm.add_argument('rpt_fn', help="area report path") 

    # create the parser for advance mode
    parser_adv = subparsers.add_parser('adv', help='advance mode')
    parser_adv.add_argument('cfg_fn', help="configuration file") 
    parser_adv.add_argument('rpt_fn', help="area report path") 

    parser_adv.add_argument('--trace', dest='trace_type', metavar='<type>', choices=['top', 'sub'],
                                        help="backward trace type")
    parser_adv.add_argument('-v', dest='is_full_dominant', action='store_true',
                                    help="show area of all trace nodes (default backtrace nodes are recessive)")

    # create the parser for black-box scan mode
    parser_bbox = subparsers.add_parser('bbox', help='black-box scan mode')
    parser_bbox.add_argument('rpt_fn', help="area report path") 

    args = parser.parse_args()

    if args.proc_mode == None:
        parser.parse_args(['-h'])

    table_attr = TableAttribute(is_show_level=args.is_show_level,
                                is_tree_view=args.is_tree_view, 
                                is_bname_view=args.is_bname_view,
                                is_ext_pathcol=args.is_ext_pathcol)

    if args.is_tree_view or args.proc_mode == 'adv' and args.trace_type is not None:
        table_attr.is_full_trace = True

    ## Main process

    global top_node

    total_bbox_area = load_area(args.rpt_fn, args.proc_mode=='norm', table_attr)

    total_logic_area = top_node.total_area - total_bbox_area
    total_logic_percent = total_logic_area / top_node.total_area
    total_bbox_percednt = total_bbox_area / top_node.total_area
    area_len = int(math.log10(math.ceil(top_node.total_area))) + 6

    print()
    print(f" Top Summary ".center(32, '='))
    print("  total: {} ({:>6.1%})".format(f"{top_node.total_area:.4f}".rjust(area_len), 1.0))
    print("  logic: {} ({:>6.1%})".format(f"{total_logic_area:.4f}".rjust(area_len), total_logic_percent))
    print("   bbox: {} ({:>6.1%})".format(f"{total_bbox_area:.4f}".rjust(area_len), total_bbox_percednt))
    print("=" * 32)

    if args.proc_mode == 'norm':
        show_hier_area(top_node, table_attr)

    elif args.proc_mode == 'adv':
        load_cfg(args.cfg_fn, args.is_full_dominant, table_attr)

        if args.trace_type is None or args.trace_type == 'top':
            root_node = top_node
        else:
            root_node = top_node
            while True:
                if root_node.is_dominant:
                    break
                if len(root_node.scans) > 1:
                    break
                root_node = tuple(root_node.scans)[0]

        show_hier_area(root_node, table_attr)

    elif args.proc_mode == 'bbox':
        show_bbox_area(top_node, table_attr)

    if args.dump_fn is not None:
        with open(args.dump_fn, 'w') as f:
            scan_stack = [top_node]
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
