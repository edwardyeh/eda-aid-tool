#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-only
#
# PrimeTime Report Analysis
#
# Copyright (C) 2023 Yeh, Hsin-Hsien <yhh76227@gmail.com>
#
import argparse
import csv
import gzip
import math
import os
import re
import numpy as np
import matplotlib as mpl
import matplotlib.pyplot as plt
from decimal import Decimal, ROUND_HALF_UP
from .utils.common import str2tok
from .utils.primetime_ts import Pin, TimePath, TimeReport
from . import __version__

VERSION = f'{Path(__file__).stem} version {__version__}'


##############################################################################
### Function


class Palette:
    bar_default = '#caccd1'
    bar = (
        '#84bd00', '#efdf00', '#fe5000', '#e4002b', 
        '#da1884', '#a51890', '#0077c8', '#008eaa', 
        '#74d2e7', '#48a9c5', '#0085ad', '#8db9ca', 
        '#4298b5', '#005670', '#004182', '#44712e',
        '#915907', '#b24020', '#dce6f1', '#d7ebce',
        '#fce2ba', '#fadfd8', '#0a66c2', '#83941f',
        '#e7a33e', '#f5987e',
    )


def load_times_cfg(cfg_fp) -> dict:
    """Load configuration."""
    attr = {
        'through_pin_on_report':  ('thp_on_rpt' , True),
        'slack_on_report':        ('slk_on_rpt' , True),
        'path_info_on_report':    ('info_on_rpt', True),
        'clock_skew_on_report':   ('skew_on_rpt', True),
        'delta_sum_on_report':    ('dts_on_rpt' , True),
        'path_level_on_report':   ('plv_on_rpt' , True),
        'path_segment_on_report': ('seg_on_rpt' , True),
    }

    cons_cfg = dict(attr.values())
    cons_cfg.update({
        'cpkg': {}, 'cpin': {}, 'pc': {}, 'dpc': 'TP', 'hcd': {}, 
        'bds': {}, 'cc': {}, 'dc_re': [], 'dc': {},
    })

    if cfg_fp is None:
        return cons_cfg

    with open(cfg_fp, 'r') as fp:
        for fno, line in enumerate(fp, 1):
            line = line.split('#')[0].strip()
            if line:
                try:
                    key, value = line.split(':')
                    key, value = key.strip(), value.strip()
                    if key in attr:
                        if value.lower() == 'true':
                            cons_cfg[attr[key][0]] = True
                        elif value.lower() == 'false':
                            cons_cfg[attr[key][0]] = False
                        else:
                            raise SyntaxError
                    elif key == 'cpkg':
                        pkg, pat = value.split()
                        cpkg_list = cons_cfg['cpkg'].setdefault(pkg, [])
                        cpkg_list.append(re.compile(pat))
                    elif key == 'cpin':
                        pkg, type_, pat, *pins = value.split()
                        if pat != '*':
                            pat = re.compile(pat)
                        cpin_dict = cons_cfg['cpin'].setdefault(pkg, {'c': [], 'o': []})
                        match type_:
                            case 'c': cpin_dict[type_].append((pat, set(pins)))
                            case 'o': cpin_dict[type_].append((pat, set(pins)))
                            case  _ : raise SyntaxError
                    elif key == 'pc':
                        tag, pat = value.split()
                        cons_cfg['pc'][tag] = re.compile(pat)
                    elif key == 'dpc':
                        cons_cfg['dpc'] = value
                    elif key == 'hcd':
                        type_, pi, po, tag = str2tok(value)
                        hcd_dict = cons_cfg['hcd'].setdefault(type_, {})
                        hcd_dict[f'{pi}:{po}'] = tag
                    elif key == 'bds':
                        grp, *type_ = value.split()
                        cons_cfg['bds'][grp] = set(type_)
                    elif key == 'cc':
                        tag, pat = value.split()
                        cons_cfg['cc'][tag] = re.compile(pat)
                    elif key == 'dc':
                        v1, *v2 = value.split()
                        if v1 == 'r':
                            for pat in v2:
                                cons_cfg['dc_re'].append(re.compile(pat))
                        else:
                            cons_cfg['dc'][v2[0]] = float(v1)
                except Exception:
                    raise SyntaxError(f'config syntax error (ln:{fno})')

    return cons_cfg


def report_summary(args, range_list: list):
    """Report the timing summary of paths."""
    cons_cfg = load_times_cfg(args.cfg_fp)
    time_rpt = TimeReport(
        cpkg=cons_cfg['cpkg'],
        cpin=cons_cfg['cpin'],
        pc=cons_cfg['pc'],
        dpc=cons_cfg['dpc'],
        hcd=cons_cfg['hcd'],
        cc=cons_cfg['cc'],
        dc=cons_cfg['dc']
    )
    time_rpt.parse_report(args.rpt_fp, range_list, args.is_debug)

    if args.is_debug:
        print('\n=== Configure:')
        for key, value in cons_cfg.items():
            print(f'{key}: {value}')
        print('\n=== Option:')
        print(time_rpt.opt)
        for no, path in enumerate(time_rpt.path, 1):
            print(f'\n=== Path {no}:')
            msg = path.__repr__()
            for line in msg.split(','):
                print(line)
        return

    ### display summary
    def check_sub_div(is_sub_div: bool):
        if not is_sub_div:
            print(' {}'.format('-' * 60))
        return True

    for pid, path in enumerate(time_rpt.path):
        div1 = ' {}'.format('=' * 60)
        div2 = ' {}'.format('-' * 60)
        sc_type = f'({path.sed} {path.sck})'
        ec_type = f'({path.eed} {path.eck})'
        stp = path.dpath[0].name
        edp = path.dpath[-1].name

        plen = len(stp)
        if (newlen:=len(edp)) > plen:
            plen = newlen

        strlen = len(f'{stp} {sc_type}')
        if (newlen:=len(f'{edp} {ec_type}')) > strlen:
            strlen = newlen

        ## path information
        print(div1)
        if strlen > 80:
            print(' Startpoint: {}'.format(stp))
            print('             {}'.format(sc_type))
            print(' Endpoint:   {}'.format(edp))
            print('             {}'.format(ec_type))
        else:
            print(' Startpoint: {} {}'.format(stp.ljust(plen), sc_type))
            print(' Endpoint:   {} {}'.format(edp.ljust(plen), ec_type))
        print(' Path group: {}'.format(path.group))
        print(' Delay type: {}'.format(path.type))
        if path.scen is not None:
            print(' Scenario:   {}'.format(path.scen))
        if cons_cfg['thp_on_rpt'] and len(path.thp):
            print(div2)
            for thp in path.thp:
                print(' Through:    {}'.format(thp))
        print(div1)

        ## path latency
        if cons_cfg['slk_on_rpt']:
            print(' {:26}{: 5.4f}'.format('data latency:', path.dlat))
            print(' {:26}{: 5.4f}'.format('arrival:', path.arr))
            print(' {:26}{: 5.4f}'.format('required:', path.req))
            print(' {:26}{: 5.4f}'.format('slack:', path.slk))
            if cons_cfg['info_on_rpt']:
                is_sub_div = False
                if path.slk != math.inf and path.cpg:
                    is_sub_div = check_sub_div(is_sub_div)
                    print(' {:26}{: 5.4f}'.format('clock uncertainty:', path.unce))
                if path.dpath[-1].cell not in ('out', 'inout') and path.lib is not None:
                    is_sub_div = check_sub_div(is_sub_div)
                    desc = f'library {'setup' if path.type == 'max' else 'hold'}:'
                    print(' {:26}{: 5.4f}'.format(desc, path.lib))
                if path.idly_en:
                    is_sub_div = check_sub_div(is_sub_div)
                    print(' {:26}{: 5.4f}'.format('input delay:', path.idly))
                if path.odly_en:
                    is_sub_div = check_sub_div(is_sub_div)
                    print(' {:26}{: 5.4f}'.format('output delay:', path.odly))
                if path.pmag_en:
                    is_sub_div = check_sub_div(is_sub_div)
                    print(' {:26}{: 5.4f}'.format('path margin:', path.pmag))
                if len(path.hcd):
                    strlen = max([len(x) for x, y in path.hcd])
                    strlen = (strlen + 1) if strlen > 25 else 26
                    print(div2)
                    for tag, value in path.hcd:
                        print(' {}{: 5.4f}'.format(tag.ljust(strlen), value))
            print(div1)

        ## clock latency & check
        if cons_cfg['skew_on_rpt']:
            is_sub_div = True
            if path.edly_en:
                is_sub_div = False
                print(' {:26}{: 5.4f}'.format('max delay:', path.edly))
            if path.slk != math.inf and not path.edly_en:
                print(' {:26}{: 5.4f}'.format('launch clock edge value:', path.sedv))
                print(' {:26}{: 5.4f}'.format('capture clock edge value:', path.eedv))
            if path.lpg:
                is_sub_div = check_sub_div(is_sub_div)
                print(' {:26}{: 5.4f}'.format('launch clock latency:', path.llat))
            if path.cpg:
                is_sub_div = check_sub_div(is_sub_div)
                print(' {:26}{: 5.4f}'.format('capture clock latency:', path.clat))
            if path.slk != math.inf and path.lpg and path.cpg:
                is_sub_div = check_sub_div(is_sub_div)
                print(' {:26}{: 5.4f}'.format('crpr:', path.crpr))
                print(' {:26}{: 5.4f}'.format('clock skew:', path.skew))
            print(div1)

        ## path delta / path level
        is_div_end = False

        if cons_cfg['dts_on_rpt'] and 'delta' in time_rpt.opt:
            is_div_end = True
            dts_tag = 'D/'
            dts_val = '{: 5.4f}/'.format(path.ddt)
            if 'pf' not in time_rpt.opt:
                if len(path.lpath):
                    dts_tag += 'L/'
                    dts_val += '{:5.4f}/'.format(path.ldt)
                if len(path.cpath):
                    dts_tag += 'C/'
                    dts_val += '{:5.4f}/'.format(path.cdt)
            dts_tag = dts_tag[:-1]
            dts_val = dts_val[:-1]
            print(' {:26}{}'.format(f'delta sum  ({dts_tag}):', dts_val))

        if cons_cfg['plv_on_rpt']:
            is_div_end = True
            dlvl_tag = 'D/'
            dlvl_val = '{: d}/'.format(path.dlvl)
            if 'pf' not in time_rpt.opt:
                if path.comp is not None:
                    dlvl_tag += 'CP/'
                    dlvl_val += '{:d}/'.format(path.cclvl)
                if len(path.lpath):
                    dlvl_tag += 'L/'
                    dlvl_val += '{:d}/'.format(path.llvl)
                if len(path.cpath):
                    dlvl_tag += 'C/'
                    dlvl_val += '{:d}/'.format(path.clvl)
            dlvl_tag = dlvl_tag[:-1]
            dlvl_val = dlvl_val[:-1]
            print(' {:26}{}'.format(f'path level ({dlvl_tag}):', dlvl_val))

        if is_div_end:
            print(div1)

        ## path segment
        if cons_cfg['seg_on_rpt'] and len(cons_cfg['pc']) == 0:
            print(' Segment: path classify patterns is unexisted.')
            print(div1)
        elif cons_cfg['seg_on_rpt']:
            if 'pf' in time_rpt.opt:
                print(' Segment:  (report path type: full)')
            elif 'pfc' in time_rpt.opt:
                print(' Segment:  (report path type: full_clock)')
            elif 'pfce' in time_rpt.opt:
                print(' Segment:  (report path type: full_clock_expanded)')
            else:
                print(' Segment:  (report path type: unknown)')

            # data latency & delta
            print(div2)
            msg_str = ''
            for tag, value in path.dlat_seg:
                msg_str += '{}:{: 5.4f} '.format(tag, value)
            print(' {:14s}{}'.format('data latency:', msg_str))
            if 'delta' in time_rpt.opt:
                msg_str = ''
                for tag, value in path.ddt_seg:
                    msg_str += '{}:{: 5.4f} '.format(tag, value)
                print(' {:14s}{}'.format('data delta:', msg_str))

            # launch clock latency & delta
            if 'pf' not in time_rpt.opt and len(path.lpath):
                print(div2)
                msg_str = ''
                for tag, value in path.llat_seg:
                    msg_str += '{}:{: 5.4f} '.format(tag, value)
                msg_str += ' (SC:{: 5.4f} COM:{: 5.4f})'.format(path.llat_sc, path.llat_com)
                print(' {:21s}{}'.format('launch clk latency:', msg_str))
                if 'delta' in time_rpt.opt:
                    msg_str = ''
                    for tag, value in path.ldt_seg:
                        msg_str += '{}:{: 5.4f} '.format(tag, value)
                    print(' {:21s}{}'.format('launch clk delta:', msg_str))

            # capture clock latency & delta
            if 'pf' not in time_rpt.opt and len(path.cpath):
                print(div2)
                msg_str = ''
                for tag, value in path.clat_seg:
                    msg_str += '{}:{: 5.4f} '.format(tag, value)
                clat_com = path.clat_com + path.crpr
                msg_str += ' (SC:{: 5.4f} COM:{: 5.4f})'.format(path.clat_sc, clat_com)
                print(' {:21s}{}'.format('capture clk latency:', msg_str))
                if 'delta' in time_rpt.opt:
                    msg_str = ''
                    for tag, value in path.cdt_seg:
                        msg_str += '{}:{: 5.4f} '.format(tag, value)
                    print(' {:21s}{}'.format('capture clk delta:', msg_str))

            print(div1)
        print()

    ### show time bar chart
    if args.show_bar:
        bar_dtype = None
        if args.bar_set is not None:
            if len(cons_cfg['bds']) and args.bar_set in cons_cfg['bds']:
                bar_dtype = cons_cfg['bds'][args.bar_set]
            else:
                print('[WARNING] Cannot found the bar set in the config, ignore.')
        elif args.bar_dtype is not None:
            bar_dtype = args.bar_dtype

        if bar_dtype is None:
            bar_dtype = ['c','t','d','i','ct']

        if args.bar_ptype is not None:
            bar_ptype = args.bar_ptype
        else:
            bar_ptype = ['a']

        show_time_bar(time_rpt.path[-1], time_rpt.opt, cons_cfg, 
                      bar_dtype, bar_ptype, args.bar_rev)


def show_time_bar(path: TimePath, path_opt: set, cons_cfg: dict, 
                  bar_dtype: list, bar_ptype: list, is_rev: bool):
    """
    Show the time path on the barchart.

    Arguments
    ---------
    path      : path data.
    path_opt  : report options.
    cons_cfg  : configurations.
    bar_dtype : data type of a barchart.
    bar_ptype : path type of a barchart.
    is_rev    : axis reverse.
    """
    dtype_info = {
        'c' : {'tag': 'cap'  , 'title': 'Cap (pf)'  },
        't' : {'tag': 'tran' , 'title': 'Tran (ns)' },
        'd' : {'tag': 'delta', 'title': 'Delta (ns)'},
        'i' : {'tag': 'incr' , 'title': 'Incr (ns)' },
        'ct': {'tag': 'cell' , 'title': 'Cell Type' },
    }

    ptype_info = {
        'a': 'Arrival Timing Path',
        'l': 'Launch Clock Path',
        'c': 'Capture Clock Path',
        'd': 'Data Path',
    }

    db, db_dict, = [], {}
    for dtype in bar_dtype:
        if dtype not in dtype_info or dtype_info[dtype]['tag'] not in path_opt:
            continue
        db_dict[dtype], clist, dlist = {}, [], []

        dir_type = set()
        if dtype in ('t', 'd', 'i'):
            dir_type.add('in')
        if dtype in ('c', 't', 'i'):
            dir_type.add('out')

        for ptype in bar_ptype:
            if ptype == 'a' or ptype == 'l':
                for pin in path.lpath:
                    if pin.type != 'hier' and pin.dir in dir_type:
                        clist.append(pin)
            if ptype == 'a' or ptype == 'd':
                for pin in path.dpath:
                    if pin.type != 'hier' and pin.dir in dir_type:
                        dlist.append(pin)
            if ptype == 'c':
                for pin in path.cpath:
                    if pin.type != 'hier' and pin.dir in dir_type:
                        clist.append(pin)

            db_dict[dtype][ptype] = []
            if len(clist):
                db_dict[dtype][ptype].append(clist)
            if len(dlist):
                db_dict[dtype][ptype].append(dlist)
            if len(db_dict[dtype][ptype]) == 2:
                del db_dict[dtype][ptype][1][0]

    if 'ct' in bar_dtype:
        db_dict['ct'], clist, dlist = {}, [], []

        for ptype in bar_ptype:
            if ptype == 'a' or ptype == 'l':
                for pin in path.lpath:
                    if pin.type == 'end' or (pin.type != 'hier' and pin.dir == 'out'):
                        clist.append(pin)
            if ptype == 'a' or ptype == 'd':
                for pin in path.dpath:
                    if pin.type == 'end' or (pin.type != 'hier' and pin.dir == 'out'):
                        dlist.append(pin)
            if ptype == 'c':
                for pin in path.cpath:
                    if pin.type == 'end' or (pin.type != 'hier' and pin.dir == 'out'):
                        clist.append(pin)

            db_dict['ct'][ptype] = []
            if len(clist):
                db_dict['ct'][ptype].append(clist)
            if len(dlist):
                db_dict['ct'][ptype].append(dlist)
            if len(db_dict['ct'][ptype]) == 2:
                del db_dict['ct'][ptype][1][0]

    if len(db_dict) and len(db_dict[list(db_dict)[0]]):
        dtype_list = list(db_dict)
        ptype_list = list(db_dict[dtype_list[0]])
        dtype_cnt, ptype_cnt = len(dtype_list), len(ptype_list)

        if is_rev:
            cy_cnt, cx_cnt = ptype_cnt, dtype_cnt
        else:
            cy_cnt, cx_cnt = dtype_cnt, ptype_cnt

        fig, axs = plt.subplots(cy_cnt, cx_cnt, constrained_layout=True)
        bbox = dict(boxstyle='round', fc='#ffcc00', alpha=0.6)
        arrow = dict(arrowstyle='->', connectionstyle="arc3,rad=0.")

        pt_anno_list = [[] for i in range(dtype_cnt*ptype_cnt)]

        for y, (dtype, dtype_dict) in enumerate(db_dict.items()):
            for x, (ptype, ptype_list) in enumerate(dtype_dict.items()):
                bar_info = get_time_bar_info(dtype_info[dtype]['tag'], cons_cfg, ptype_list)

                ## get sub plot
                if is_rev:
                    aid = cx_cnt * x + y
                else:
                    aid = cx_cnt * y + x
                axs = plt.subplot(cy_cnt, cx_cnt, aid+1)
                plt.rcParams['hatch.linewidth'] = 2

                ## setting canvas
                axs.grid(axis='y', which='both', ls=':', c='grey')
                axs.set_xticks(range(len(bar_info['cv'])))

                min_iy = min(bar_info['cv'])
                if min_iy > 0:
                    min_iy = 0

                max_iy = max(bar_info['cv'])
                if dtype == 'ct':
                    off_iy = 0.5
                    max_iy = round(max_iy + 1)
                else:
                    if max_iy < 0.1:
                        off_iy = 0.01
                    elif max_iy < 1.0:
                        off_iy = 0.1
                    else:
                        off_iy = max_iy / 10
                    max_iy = max_iy + off_iy * 2

                axs.set_ylim(top=max_iy)
                axs.set_yticks(np.arange(min_iy, max_iy, off_iy))

                ## add legend & title
                label_list, handle_list = [], []
                for label, color in bar_info['lg'].items():
                    label_list.append(label)
                    handle_list.append(plt.Rectangle((0,0), 1, 1, color=color))
                axs.legend(handle_list, label_list, loc='upper left', ncol=len(label_list))
                axs.set_title(f'{ptype_info[ptype]} {dtype_info[dtype]['title']}')

                ## draw canvas & add annotation
                off_ty = max_iy - min_iy
                min_ty = min_iy
                tx = -0.5
                ty_ratio = 0.5
                ty = min_ty + off_ty * ty_ratio

                for ix, iy in enumerate(bar_info['cv']):
                    # plot
                    if dtype == 'ct':
                        pt, = axs.bar(ix, 0.25, width=1.0, 
                                      color=bar_info['c'][ix], 
                                      hatch=bar_info['ha'][ix], 
                                      ec=bar_info['ec'][ix])

                        axs.stem(ix, iy)
                    else:
                        pt, = axs.bar(ix, iy, width=1.0, 
                                      color=bar_info['c'][ix], 
                                      hatch=bar_info['ha'][ix], 
                                      ec=bar_info['ec'][ix])
                    # annotation
                    toks = bar_info['pin'][ix].name.split('/')
                    if len(toks) > 2:
                        name = f".../{toks[-2]}/{toks[-1]}"
                    else:
                        name = bar_info['pin'][ix].name
                    val = "val: {:.4f}".format(iy:=bar_info['cv'][ix])
                    comm = "pin: {}\n{}\nln: {}".format(name, val, bar_info['pin'][ix].ln)
                    anno = plt.annotate(comm, xy=(ix,iy), xytext=(tx,ty), 
                                        bbox=bbox, arrowprops=arrow, size=10)
                    anno.set_visible(False)
                    info = {'tx': tx, 'min_ty': min_ty, 
                            'off_ty': off_ty, 'ty_ratio': ty_ratio, 
                            'ce': bar_info['pin'][ix], 'plv': 2, 
                            'ct': False}
                    pt_anno_list[aid].append([pt, anno, info])

        def on_move(event):
            is_vis_chg = False
            for i in range(len(pt_anno_list)):
                for pt, anno, _ in pt_anno_list[i]:
                    is_vis = (pt.contains(event)[0] == True)
                    if is_vis != anno.get_visible():
                        is_vis_chg = True
                        anno.set_visible(is_vis)
            if is_vis_chg:
                plt.draw()

        def on_mouse(event):
            ev_key = str(event.button)
            if ev_key in {'MouseButton.LEFT', '1'}:
                for i in range(len(pt_anno_list)):
                    is_act, vis_list = False, []
                    for pt, *_ in pt_anno_list[i]:
                        vis_list.append(pt.contains(event)[0] == True)
                        is_act = is_act or vis_list[-1]
                    if is_act:
                        for is_vis, pt_anno in zip(vis_list, pt_anno_list[i]):
                            if is_vis != pt_anno[1].get_visible():
                                pt_anno[1].set_visible(is_vis)
            elif ev_key in {'MouseButton.RIGHT', '3'}:
                for i in range(len(pt_anno_list)):
                    for pt, anno, _ in pt_anno_list[i]:
                        anno.set_visible(False)
            plt.draw()

        def on_key(event):
            ev_key, val = key_event_check(str(event.key))
            # print(str(event.key), ev_key, val)
            match ev_key:
                case 'ESC':
                    for i in range(len(pt_anno_list)):
                        for pt, anno, _ in pt_anno_list[i]:
                            anno.set_visible(False)
                    plt.draw()
                case 'UD':
                    for i in range(len(pt_anno_list)):
                        for pt, anno, info in pt_anno_list[i]:
                            info['ty_ratio'] += val 
                            anno.set_y(info['min_ty'] + info['off_ty'] * info['ty_ratio'])
                    plt.draw()
                case 'LR':
                    for i in range(len(pt_anno_list)):
                        for pt, anno, info in pt_anno_list[i]:
                            anno.set_x(anno._x + val)
                    plt.draw()
                case 'PM':
                    for i in range(len(pt_anno_list)):
                        for pt, anno, info in pt_anno_list[i]:
                            info['plv'] = (plv:=info['plv']) + val
                            toks = (name:=info['ce'].name).split('/')
                            if len(toks) > plv:
                                name = ""
                                for i in range(-1, -1-plv, -1):
                                    name = "/{}".format(toks[i]) + name 
                                name = '...' +name 
                            toks = anno.get_text().split('\n')
                            anno.set_text(f"pin: {name}\n{toks[-2]}\n{toks[-1]}")
                    plt.draw()
                case 'BT':
                    for i in range(len(pt_anno_list)):
                        for pt, anno, info in pt_anno_list[i]:
                            toks = anno.get_text().split('\n')
                            if val == 2 and info['ct'] is False:
                                toks[0] = "{}\nlib: {}".format(toks[0], info['ce'].cell)
                            anno.set_text(f"{toks[0]}\n{toks[-2]}\n{toks[-1]}")
                    plt.draw()
                case 'RESET':
                    for i in range(len(pt_anno_list)):
                        for pt, anno, info in pt_anno_list[i]:
                            if anno._x == -0.5 and info['ty_ratio'] == 0.5:
                                info['plv'] = 2
                                toks = (name:=info['ce'].name).split('/')
                                if len(toks) > 2:
                                    name = f'.../{toks[-2]}/{toks[-1]}'
                                toks = anno.get_text().split('\n')
                                anno.set_text(f"pin: {name}\n{toks[-2]}\n{toks[-1]}")
                            info['ty_ratio'] = 0.5
                            anno.set_x(tx)
                            anno.set_y(info['min_ty'] + info['off_ty'] * info['ty_ratio'])
                    plt.draw()

        # fig.canvas.mpl_connect('motion_notify_event', on_move)
        fig.canvas.mpl_connect('button_press_event', on_mouse)
        fig.canvas.mpl_connect('key_press_event', on_key)
        plt.show()


def get_time_bar_info(attr: str, cons_cfg: dict, ptype_list: list):
    """
    Get the time bar information.

    Arguments
    ---------
    attr       : cell attribute for the type classification.
    cons_cfg   : configurations.
    ptype_list : pin lists of the path type.

    Returns
    -------
    bar_info : the information of the barchart. (type: dict) 
    """
    pal_cnt = len(Palette.bar)
    if attr == 'cell':
        bar_palette = {'UN': Palette.bar_default}
        for i, key in enumerate(cons_cfg['cc'].keys()):
            bar_palette[key] = Palette.bar[i%pal_cnt]
    else:
        bar_palette = {cons_cfg['dpc']: Palette.bar_default}
        for i, key in enumerate(cons_cfg['pc'].keys()):
            bar_palette[key] = Palette.bar[i%pal_cnt]

    bar_info = {
        'pin': [],  # pin object
        'cv' : [],  # cell value of each bar
        'c'  : [],  # color of each bar
        'ha' : [],  # hatch pattern of each bar
        'ec' : [],  # edge color of each bar
        'lg' : {},  # legend dict
        'dsp': []   # data startpoint index
    }
    tag_set = set() 

    is_first = True
    for pin_list in ptype_list:
        if not is_first:
            idx = len(bar_info['cv']) - 1
            bar_info['dsp'].append(idx)
            bar_info['ha'][idx] = '/'
            bar_info['ec'][idx] = 'b'

        for pin in pin_list:
            ## get the cell value and make the classification
            if attr == 'cell':
                tag, cv = 'UN', 0.0
                if len(cons_cfg['cc']) and len(cons_cfg['dc']):
                    cname = pin.__dict__['cell']
                    for key, cc_pat in cons_cfg['cc'].items():
                        if cc_pat.fullmatch(cname):
                            for dc_pat in cons_cfg['dc_re']:
                                if (m:=dc_pat.fullmatch(cname)):
                                    for drv_pat, drv_cv in cons_cfg['dc'].items():
                                        if m[1] == drv_pat:
                                            tag, cv = key, drv_cv
                                            break
                                    break
                            break
            else:
                tag, cv = cons_cfg['dpc'], float(pin.__dict__[attr])
                if len(cons_cfg['pc']):
                    for key, pat in cons_cfg['pc'].items():
                        if pat.fullmatch(pin.__dict__['name']):
                            tag = key
                            break
            tag_set.add(tag)
            bar_info['pin'].append(pin)
            bar_info['cv'].append(cv)
            bar_info['c'].append(bar_palette[tag])
            bar_info['ha'].append('')
            bar_info['ec'].append('k')
        is_first = False

    for key, val in bar_palette.items():
        if key in tag_set:
            bar_info['lg'][key] = val

    return bar_info


def key_event_check(action):
    """Check Key Event"""
    if action == 'escape': return 'ESC'  ,  0    # remove all comment bubble
    if action == 'up':     return 'UD'   ,  0.1  # up shift bubble
    if action == 'down':   return 'UD'   , -0.1  # down shift bubble
    if action == 'left':   return 'LR'   , -0.5  # left shift bubble
    if action == 'right':  return 'LR'   ,  0.5  # right shift bubble
    if action == 'a':      return 'PM'   ,  1    # increase pin hierarchical
    if action == 'd':      return 'PM'   , -1    # decrease pin hierarchical
    if action == '1':      return 'BT'   ,  1    # bubble type 1 (pin, val, ln)
    if action == '2':      return 'BT'   ,  2    # bubble type 2 (pin, lib, val, ln)
    if action == 'r':      return 'RESET',  0    # reset bubble
    return "NONE", 0


##############################################################################
### Main


def create_argparse() -> argparse.ArgumentParser:
    """Create Argument Parser"""
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawTextHelpFormatter,
        description='PrimeTime Report Analysis\n' + 
                    '  -- Timing Path Summary\n' +
                    '  -- Command: report_timing')

    parser.add_argument('rpt_fp', help='Report file path') 
    parser.add_argument('-version', action='version', version=VERSION)
    parser.add_argument('-debug', dest='is_debug', action='store_true', 
                            help='enable debug mode\n ')
    parser.add_argument('-c', dest='cfg_fp', metavar='<config>', 
                            help='config file path') 
    parser.add_argument('-nc', dest='is_nocfg', action='store_true', 
                            help='disable to load the config file')
    parser.add_argument('-r', dest='range', metavar='<value>', 
                            help='report scan range (default: load 1 path from line 0)\n' + 
                                 'format: start[:end][+count],start2[:end2][+count2], ...\n ') 
    parser.add_argument('-bar', dest='show_bar', action='store_true', 
                            help='show bar chart')
    parser.add_argument('-bard', dest='bar_dtype', metavar='<pat>', nargs='+', 
                            choices=['c','t','d','i', 'ct'],
                            help='bar chart data type (default: all types)\n' +
                                 'c: cap, t: tran, d: delta, i: incr, ct: cell_type') 
    parser.add_argument('-barp', dest='bar_ptype', metavar='<pat>', nargs='+', 
                            choices=['a','d','l','c'],
                            help='bar chart path type (default: arrival time)\n' +
                                 'a: arrival path, d: data path, l: launch clock path, c: capture clock path') 
    parser.add_argument('-bars', dest='bar_set', metavar='<tag>', 
                            help='data type set of the bar chart defined in the config file') 
    parser.add_argument('-barr', dest='bar_rev', action='store_true', 
                            help='bar chart axis reverse\n ')
    return parser


def main():
    """Main Function"""
    parser = create_argparse()
    args = parser.parse_args()
    default_cfg = '.pt_ana_ts.setup'

    if args.is_nocfg:
        args.cfg_fp = None
    elif args.cfg_fp is None and os.path.exists(default_cfg):
        if os.path.isfile(default_cfg):
            args.cfg_fp = default_cfg

    range_list = []
    if args.range is not None:
        range_re = re.compile(r'(?P<st>\d+)(?::(?P<ed>\d+))?(?:\+(?P<nu>\d+))?')
        for range_ in args.range.split(','):
            if (m:=range_re.fullmatch(range_)):
                st = int(m.group('st'))
                ed = None if (ed:=m.group('ed')) is None else int(ed)
                nu = None if (nu:=m.group('nu')) is None else int(nu)
                range_list.append([st, ed, nu])
    if not range_list:
        range_list.append([0, None, 1])  # [start_line, last_line, path_count]
    
    print('\n Report: {}\n'.format(os.path.abspath(args.rpt_fp)))
    report_summary(args, range_list)


if __name__ == '__main__':
    main()


