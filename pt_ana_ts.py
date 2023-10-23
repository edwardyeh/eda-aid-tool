#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-only
#
# PrimeTime Report Analysis
#
# Copyright (C) 2023 Yeh, Hsin-Hsien <yhh76227@gmail.com>
#
import argparse
import gzip
import os
import re

import numpy as np
import matplotlib as mpl
import matplotlib.pyplot as plt

from .utils.common import PKG_VERSION, PT_TS_VER
from .utils.primetime_ts import Pin, TimePath, TimeReport

VERSION = f"pt_ana_ts version {PT_TS_VER} ({PKG_VERSION})"


##############################################################################
### Function


class Palette:
    hist_default = "#caccd1"
    hist = (
        "#84bd00", "#efdf00", "#fe5000", "#e4002b", 
        "#da1884", "#a51890", "#0077c8", "#008eaa", 
        "#74d2e7", "#48a9c5", "#0085ad", "#8db9ca", 
        "#4298b5", "#005670", "#004182", "#44712e",
        "#915907", "#b24020", "#dce6f1", "#d7ebce",
        "#fce2ba", "#fadfd8", "#0a66c2", "#83941f",
        "#e7a33e", "#f5987e",
    )


def load_times_cfg(cfg_fp) -> dict:
    """Load configuration."""
    attr = {
        'clock_check_enable':                    ('ckc_en'         , False),
        'delta_sum_enable':                      ('dts_en'         , False),
        'path_segment_enable':                   ('seg_en'         , False),
        'ckm_with_non_clock_cell':               ('ckm_nock'       , False),
        'slack_on_report':                       ('slk_on_rpt'     , True),
        'clock_uncertainty_on_report':           ('unce_on_rpt'    , False),
        'library_required_on_report':            ('lib_on_rpt'     , False),
        'clock_skew_on_report':                  ('ck_skew_on_rpt' , True),
        'segment_data_latency_on_report':        ('seg_dlat_on_rpt', True),
        "segment_data_delta_on_report":          ('seg_ddt_on_rpt' , True),
        'segment_launch_clk_latency_on_report':  ('seg_slat_on_rpt', True),
        'segment_launch_clk_delta_on_report':    ('seg_sdt_on_rpt' , True),
        'segment_capture_clk_latency_on_report': ('seg_elat_on_rpt', True),
        'segment_capture_clk_delta_on_report':   ('seg_edt_on_rpt' , True),
    }

    cons_cfg = dict(attr.values())
    cons_cfg.update({
        'bds': {}, 'ckpc': set(), 'ckpi': set(), 'ckpr': [],
        'hcd': {},  # format: {cell: {'pi:po': tag, ...}, ...}
        'ckt': [], 'ckm': [], 'dpc': None, 'pc': {}, 'cc': {},
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
                        change_value = str(not attr[key][1]).lower()
                        if value.lower() == change_value:
                            cons_cfg[attr[key][0]] = not attr[key][1]
                        else:
                            cons_cfg[attr[key][0]] = attr[key][1]
                    elif key == 'bds':
                        tag, *pat = value.split()
                        cons_cfg['bds'][tag] = pat
                    elif key == 'ckt':
                        tag, pat = value.split()
                        pat_re = re.compile(pat)
                        match tag.lower():
                            case 'y': tag = True
                            case 'n': tag = False
                            case  _ : raise SyntaxError
                        cons_cfg['ckt'].append((tag, pat_re))
                    elif key == 'ckp':
                        type_, *pat = value.split()
                        match type_:
                            case 'c': cons_cfg['ckpc'].update(pat)
                            case 'i': cons_cfg['ckpi'].update(pat)
                            case 'r': cons_cfg['ckpr'].extend(
                                        [re.compile(i) for i in pat])
                            case  _ : raise SyntaxError
                    elif key == 'ckm':
                        pat = re.compile(value.split()[0])
                        cons_cfg['ckm'].append(pat)
                    elif key == 'dpc':
                        cons_cfg['dpc'] = value
                    elif key == 'pc':
                        tag, pat = value.split()
                        cons_cfg['pc'][tag] = re.compile(pat)
                    elif key == 'cc':
                        tag, pat = value.split()
                        cons_cfg['cc'][tag] = re.compile(pat)
                    elif key == 'hcd':
                        toks = value.split('"') 
                        if len(toks) > 1:
                            type_, pi, po, tag = *toks[0].split(), toks[1]
                        else:
                            type_, pi, po, tag = toks[0].split()
                        hcd_dict = cons_cfg['hcd'].setdefault(type_, {})
                        cons_cfg['hcd'][type_][f"{pi}:{po}"] = tag
                except SyntaxError:
                    raise SyntaxError(f"config syntax error (ln:{fno})")

    if cons_cfg['dpc'] is not None and cons_cfg['dpc'] not in cons_cfg['pc']:
        print(" [INFO] Specific group for default path isn't existed," + 
                " ignore.\n")
        cons_cfg['dpc'] = None

    return cons_cfg


def report_summary(args, range_list: list):
    """Report the timing summary of paths."""
    cons_cfg = load_times_cfg(args.cfg_fp)
    time_rpt = TimeReport(
                cell_ckp=cons_cfg['ckpc'],
                inst_ckp=cons_cfg['ckpi'],
                ickp_re=cons_cfg['ckpr'],
                hcd=cons_cfg['hcd'],
                ckt=cons_cfg['ckt'],
                ckm=cons_cfg['ckm'],
                ckm_nock=cons_cfg['ckm_nock'],
                dpc=cons_cfg['dpc'],
                pc=cons_cfg['pc'])

    time_rpt.parse_report(args.rpt_fp, range_list)

    if args.is_debug:
        print("\n=== Option:")
        print(time_rpt.opt)
        for no, path in enumerate(time_rpt.path, 1):
            print(f"\n=== Path {no}:")
            msg = path.__repr__()
            for line in msg.split(','):
                print(line)
        return

    for pid, path in enumerate(time_rpt.path):
        splen = len(stp:=path.lpath[path.spin].pin)
        if (plen:=len(edp:=path.lpath[-1].pin)) < splen:
            plen = splen

        ## path information
        print(" {}".format("=" * 60))
        if path.max_dly_en:
            print(" Startpoint: {}".format(stp))
            print(" Endpoint:   {}".format(edp))
        elif plen > 80:
            print(" Startpoint: {}".format(stp))
            print("             ({} {})".format(path.sed, path.sck))
            print(" Endpoint:   {}".format(edp))
            print("             ({} {})".format(path.eed, path.eck))
        else:
            print(" Startpoint: {} ({} {})".format(stp.ljust(plen), 
                                                   path.sed, path.sck))
            print(" Endpoint:   {} ({} {})".format(edp.ljust(plen), 
                                                   path.eed, path.eck))
        print(" Path group: {}".format(path.group))
        print(" Delay type: {}".format(path.type))
        if path.scen is not None:
            print(" Scenario:   {}".format(path.scen))
        print(" {}".format("=" * 60))

        ## path latency
        if cons_cfg['slk_on_rpt']:
            print(" {:26}{: 5.4f}".format(
                "data latency:", path.arr-path.idly-path.slat-path.sev))
            print(" {:26}{: 5.4f}".format("arrival:", path.arr))
            print(" {:26}{: 5.4f}".format("required:", path.req))
            print(" {:26}{: 5.4f}".format("slack:", path.slk))

            if (path.idly_en or path.odly_en or path.pmarg_en or path.hcd or 
                cons_cfg['unce_on_rpt'] or cons_cfg['lib_on_rpt']):
                print(" {}".format("-" * 60))

            if cons_cfg['unce_on_rpt']:
                print(" {:26}{: 5.4f}".format(
                    "clock uncertainty:", path.unce))
            if cons_cfg['lib_on_rpt'] and not path.odly_en:
                print(" {:26}{: 5.4f}".format(
                    ("library setup:" if path.type == "max" 
                    else "library hold"), path.lib))
            if path.idly_en:
                print(" {:26}{: 5.4f}".format("input delay:", path.idly))
            if path.odly_en:
                print(" {:26}{: 5.4f}".format("output delay:", -1*path.odly))
            if path.pmarg_en:
                print(" {:26}{: 5.4f}".format("path margin:", path.pmarg))
            for tag, val in path.hcd.items():
                print(" {}{: 5.4f}".format(f"{tag}:".ljust(26), val))

            print(" {}".format("=" * 60))

        ## clock latency & check
        is_clk_on_rpt = False

        if cons_cfg['ck_skew_on_rpt']:
            is_clk_on_rpt = True
            if not path.max_dly_en:
                print(" {:26}{: 5.4f}".format("launch clock edge value:", 
                                                path.sev))
                print(" {:26}{: 5.4f}".format("capture clock edge value:", 
                                                path.eev))
            print(" {:26}{: 5.4f}".format("launch clock latency:", 
                                            path.slat))
            if not path.max_dly_en:
                print(" {:26}{: 5.4f}".format("capture clock latency:", 
                                                path.elat))
                print(" {:26}{: 5.4f}".format("crpr:", path.crpr))
                print(" {:26}{: 5.4f}".format("clock skew:", 
                                                path.slat-path.elat-path.crpr))

        if (args.ckc_en or cons_cfg['ckc_en']) and not path.max_dly_en:
            if is_clk_on_rpt:
                print(" {}".format("-" * 60))
            is_clk_on_rpt = True

            gcc_rslt, scc_rslt, ctc_rslt = time_rpt.clock_path_check(
                                            pid=pid, is_dump=args.ckc_dump)

            spath_len = ((path.spin+1) if path.sgpi is None 
                         else (path.spin-path.sgpi))

            epath_len = (len(path.cpath) if path.egpi is None 
                         else (len(path.cpath)-path.egpi-1))
            
            col_sz = len(split_lv:=f"{spath_len}/{epath_len}/{scc_rslt[0]}")
            print(" {:26} {}    {}".format("clock cell type check:", 
                                            ctc_rslt[0].ljust(col_sz), 
                                            ctc_rslt[1]))
            print(" {:26} {}    {}".format("clock source path match:", 
                                            gcc_rslt[0].ljust(col_sz), 
                                            gcc_rslt[1]))
            print(" {:26} {}    (ln:{}:{})".format("clock network path fork:", 
                                            split_lv, *scc_rslt[1:]))

        if path.max_dly_en:
            is_clk_on_rpt = True
            print(" {:26}{: 5.4f}".format("max delay:", path.max_dly))

        if is_clk_on_rpt or path.max_dly_en:
            print(" {}".format("=" * 60))

        ## clock & path delta
        if args.dts_en or cons_cfg['dts_en']:
            if 'delta' in time_rpt.opt:
                ddt_val = "{: 5.4f}".format(path.ddt)
                if not {'pfc', 'pfce'}.isdisjoint(time_rpt.opt):
                    sdt_val = "{:5.4f}".format(path.sdt)
                    edt_val = "{:5.4f}".format(path.edt)
                else:
                    sdt_val, edt_val = 'N/A', 'N/A'
            else:
                ddt_val, sdt_val, edt_val = 'N/A', 'N/A', 'N/A'

            print(" {:26}{} : {} : {}".format("total delta (D:L:C):", 
                                              ddt_val, sdt_val, edt_val))
            print(" {}".format("=" * 60))

        ## path segment
        if 'pc' in cons_cfg and (args.seg_en or cons_cfg['seg_en']):
            seg_dict = time_rpt.get_path_segment(pid)

            if 'pf' in time_rpt.opt:
                is_dseg_pass, is_ckseg_pass = False, True
                print(" Segment:  (report path type: full)")
            elif 'pfc' in time_rpt.opt:
                is_dseg_pass, is_ckseg_pass = False, False
                print(" Segment:  (report path type: full_clock)")
            elif 'pfce' in time_rpt.opt:
                is_dseg_pass, is_ckseg_pass = False, False
                print(" Segment:  (report path type: full_clock_expanded)")
            else:
                is_dseg_pass, is_ckseg_pass = True, True
                print(" Segment:  (report path type: unknown)")

            # data latency & delta
            if not is_dseg_pass:
                if cons_cfg['seg_dlat_on_rpt'] or cons_cfg['seg_ddt_on_rpt']:
                    print(" {}".format("-" * 60))
                if cons_cfg['seg_dlat_on_rpt']:
                    print(" data latency: ", end='')
                    for tag, val in seg_dict['dlat']:
                        print("{}:{: .4f} ".format(tag, val), end='')
                    print()
                if cons_cfg['seg_ddt_on_rpt']:
                    print(" data delta:   ", end='')
                    for tag, val in seg_dict['ddt']:
                        print("{}:{: .4f} ".format(tag, val), end='')
                    print()

            if not is_ckseg_pass:
                # launch clock latency & delta
                if cons_cfg['seg_slat_on_rpt'] or cons_cfg['seg_sdt_on_rpt']:
                    print(" {}".format("-" * 60))
                if cons_cfg['seg_slat_on_rpt']:
                    print(" launch clk latency:  ", end='')
                    print("SC:{: .4f} ".format(path.sslat), end='')
                    for tag, val in seg_dict['slat']:
                        print("{}:{: .4f} ".format(tag, val), end='')
                    print()
                if cons_cfg['seg_sdt_on_rpt']:
                    print(" launch clk delta:    ", end='')
                    for tag, val in seg_dict['sdt']:
                        print("{}:{: .4f} ".format(tag, val), end='')
                    print()

                ## capture clock latency & delta
                if cons_cfg['seg_elat_on_rpt'] or cons_cfg['seg_edt_on_rpt']:
                    print(" {}".format("-" * 60))
                if cons_cfg['seg_elat_on_rpt']:
                    print(" capture clk latency: ", end='')
                    print("SC:{: .4f} ".format(path.eslat), end='')
                    for tag, val in seg_dict['elat']:
                        print("{}:{: .4f} ".format(tag, val), end='')
                    print()
                if cons_cfg['seg_edt_on_rpt']:
                    print(" capture clk delta:   ", end='')
                    for tag, val in seg_dict['edt']:
                        print("{}:{: .4f} ".format(tag, val), end='')
                    print()

            print(" {}".format("=" * 60))
        print()

    ## show time bar chart
    bar_dtype = set()
    if args.bars is not None:
        if 'bds' in cons_cfg and args.bars in cons_cfg['bds']:
            bar_dtype |= set(cons_cfg['bds'][args.bars])
        else:
            print(" [WARNING] The bars option cannot find" +
                  " in the configuration, ignore.\n")
    if args.bar is not None:
        bar_dtype |= (set(args.bar) if args.bar 
                      else set(['p','c','t','d','i','ct']))
    if 'ct' in bar_dtype:
        bar_dtype.add('i')

    if len(bar_dtype) != 0:
        if args.bar_ptype is None or len(args.bar_ptype) == 0:
            bar_ptype = set(['f', 'd'])
        else:
            bar_ptype = set(args.bar_ptype)
            if 'f' in bar_ptype:
                bar_ptype.add('d')

        show_time_bar(time_rpt.path[-1], time_rpt.opt, cons_cfg, 
                      bar_dtype, bar_ptype, args.bar_rev)


def show_time_bar(path: TimePath, path_opt: set, cons_cfg: dict, 
                  bar_dtype: set, bar_ptype: set, is_rev: bool):
    """Show Time Path Barchart"""
    db, db_dict = [], {}

    ## [c]apacitance
    if 'c' in bar_dtype and 'cap' in path_opt:
        db_dict['c'], data = [], []
        for cid, cell in enumerate(path.lpath):
            data.append(cell.cap)
            if cid == path.spin:
                if 'l' in bar_ptype:
                    db_dict['c'].append(["Launch Clk Cap (pf)", data.copy()])
                if 'd' not in bar_ptype:
                    data = None
                    break
                if 'f' not in bar_ptype:
                    data = [data[-1]]
        ddata = data

        if 'c' in bar_ptype:
            data = []
            for cell in path.cpath:
                data.append(cell.cap)
            db_dict['c'].append(["Capture Clk Cap (pf)", data])

        if ddata is not None:
            db_dict['c'].append(["Path Cap (pf)", ddata])
    else:
        bar_dtype.discard('c')

    dtype_list = [
        ['p', 'phy', "Distance (um)"],    # [p]hysical distance
        ['t', 'tran', "Tran (ns)"],       # [t]ransition
        ['d', 'delta', "Delta (ns)"],     # [d]elta
        ['i', 'incr', "Increment (ns)"],  # latency [i]ncrement
    ]

    for key, tag, title in dtype_list:
        if key in bar_dtype and tag in path_opt:
            db_dict[key], data = [], []
            for cid, cell in enumerate(path.lpath):
                data.append(cell[tag])
                if cid == path.spin:
                    if 'l' in bar_ptype:
                        db_dict[key].append(
                            [f"Launch Clk {title}", data.copy()])
                    if 'd' not in bar_ptype:
                        data = None
                        break
                    if 'f' not in bar_ptype:
                        data = [data[-1]]
            ddata = data

            if 'c' in bar_ptype:
                data = []
                for cell in path.cpath:
                        data.append(cell[tag])
                db_dict[key].append([f"Capture Clk {title}", data])

            if ddata is not None:
                db_dict[key].append([f"Path {title}", ddata])
        else:
            bar_dtype.discard(key)

    if 'p' in db_dict:          # physical distance
        db.extend(db_dict['p'])
    if 'c' in db_dict:          # capacitance
        c_plist = db_dict['c']
        for key, plist in db_dict.items():
            if key != 'c':
                for i, clist in enumerate(plist):
                    if len(c_plist[i]) < len(clist):
                        c_plist[i].insert(0, 0.0)
                break
        db.extend(c_plist)
    if 't' in db_dict:          # transition
        db.extend(db_dict['t'])
    if 'd' in db_dict:          # delta
        db.extend(db_dict['d'])
    if 'i' in db_dict:          # latency increment
        db.extend(db_dict['i'])

    if len(db) != 0:
        bar_info, spin_pos = get_time_bar_info(
            'pin', ('TP' if cons_cfg['dpc'] is None else cons_cfg['dpc']), 
            (cons_cfg['pc'] if 'pc' in cons_cfg else None), 
            bar_ptype, path, True)

        if 'cc' in cons_cfg and 'ct' in bar_dtype:
            bar_ct_info, spin_pos = get_time_bar_info(
                'cell', 'UN', cons_cfg['cc'], bar_ptype, path, True)
        else:
            bar_dtype.discard('ct')

        bar_ptype.discard('f')
        dtype_cnt, ptype_cnt = len(bar_dtype), len(bar_ptype)
        cy_cnt, cx_cnt = ((ptype_cnt, dtype_cnt) if is_rev 
                          else (dtype_cnt, ptype_cnt))
        fig, axs = plt.subplots(cy_cnt, cx_cnt, constrained_layout=True)

        pt_anno_list = [[] for i in range(dtype_cnt*ptype_cnt)]
        bbox = dict(boxstyle='round', fc='#ffcc00', alpha=0.6)
        arrow = dict(arrowstyle='->', connectionstyle="arc3,rad=0.")

        if 'ct' in bar_dtype:
            is_ct_chk, last_dtype = True, dtype_cnt-1
        else:
            is_ct_chk, last_dtype = False, None

        for y in range(dtype_cnt):
            if (ct_act:=(is_ct_chk and y == last_dtype)):
                slg, slv_ce, slv_c, slv_ha, slv_ec = bar_ct_info
                dtype_off = ptype_cnt * (y - 1)
            else:
                slg, slv_ce, slv_c, slv_ha, slv_ec = bar_info
                dtype_off = ptype_cnt * y

            for x in range(ptype_cnt):
                sdb = db[dtype_off+x]
                aid = (cx_cnt*x+y) if is_rev else (cx_cnt*y+x)
                labels = list(slg[x].keys())
                handles = [plt.Rectangle((0,0), 1, 1, color=slg[x][label]) 
                           for label in labels]
                level = range(0, len(sdb[1]))

                max_dy = max(sdb[1])
                min_dy = 0 if (min_dy:=min(sdb[1])) > 0 else min_dy
                dy_off = 2.0 if ct_act else (max_dy-min_dy)
                dx, dy_rt = -0.5, 0.5
                dy = min_dy + dy_off * dy_rt

                xlist = [*level]
                if spin_pos[0] is not None and spin_pos[0] == x:
                    xlist.append(xlist[spin_pos[1]])
                    del xlist[spin_pos[1]]

                axs = plt.subplot(cy_cnt, cx_cnt, aid+1)
                for ix in xlist:
                    toks = slv_ce[x][ix].pin.split('/')
                    pin = (f".../{toks[-2]}/{toks[-1]}" if len(toks) > 2 
                           else slv_ce[x][ix].pin)
                    if ct_act:
                        val, iy = f"lib: {slv_ce[x][ix].cell}", 0.5
                    else:
                        val = "val: {:.4f}".format(iy:=sdb[1][ix])

                    comm = "pin: {}\n{}\nln: {}".format(
                                pin, val, slv_ce[x][ix].ln)
                    pt, = axs.bar(ix, iy, width=1.0, 
                                  color=slv_c[x][ix], hatch=slv_ha[x][ix], 
                                  ec=slv_ec[x][ix])
                    anno = plt.annotate(comm, xy=(ix,iy), xytext=(dx,dy), 
                                        bbox=bbox, arrowprops=arrow, size=10)
                    anno.set_visible(False)
                    info = {'dx': dx, 'min_dy': min_dy, 
                            'dy_off': dy_off, 'dy_rt': dy_rt, 
                            'ce': slv_ce[x][ix], 'plv': 2, 'ct': ct_act}
                    pt_anno_list[aid].append([pt, anno, info])

                if ct_act:
                    axs.set_title(sdb[0].split()[0] + " Cell Type")
                    axs.set_ylim(0, 2)
                else:
                    axs.set_title(sdb[0])
                axs.grid(axis='y', which='both', ls=':', c='grey')
                axs.set_xticks(level, [])
                axs.legend(handles, labels, loc='upper left', ncol=len(labels))

        # def on_move(event):
        #     is_vis_chg = False
        #     for i in range(len(pt_anno_list)):
        #         for pt, anno, _ in pt_anno_list[i]:
        #             is_vis = (pt.contains(event)[0] == True)
        #             if is_vis != anno.get_visible():
        #                 is_vis_chg = True
        #                 anno.set_visible(is_vis)
        #     if is_vis_chg:
        #         plt.draw()

        def on_mouse(event):
            ev_key = str(event.button)
            # print(ev_key)
            if ev_key == 'MouseButton.LEFT':
                for i in range(len(pt_anno_list)):
                    is_act, vis_list = False, []
                    for pt, *_ in pt_anno_list[i]:
                        vis_list.append(pt.contains(event)[0] == True)
                        is_act = is_act or vis_list[-1]
                    if is_act:
                        for is_vis, pt_anno in zip(vis_list, pt_anno_list[i]):
                            if is_vis != pt_anno[1].get_visible():
                                pt_anno[1].set_visible(is_vis)
            elif ev_key == 'MouseButton.RIGHT':
                for i in range(len(pt_anno_list)):
                    for pt, anno, _ in pt_anno_list[i]:
                        anno.set_visible(False)
            plt.draw()

        def on_key(event):
            ev_key, val = key_event_check(str(event.key))
            # print(str(event.key))
            match ev_key:
                case 'ESC':
                    for i in range(len(pt_anno_list)):
                        for pt, anno, _ in pt_anno_list[i]:
                            anno.set_visible(False)
                    plt.draw()
                case 'UD':
                    for i in range(len(pt_anno_list)):
                        for pt, anno, info in pt_anno_list[i]:
                            info['dy_rt'] += val 
                            anno.set_y(info['min_dy']
                                       + info['dy_off']*info['dy_rt'])
                    plt.draw()
                case 'LR':
                    for i in range(len(pt_anno_list)):
                        for pt, anno, info in pt_anno_list[i]:
                            anno.set_x(anno._x+val)
                    plt.draw()
                case 'PM':
                    for i in range(len(pt_anno_list)):
                        for pt, anno, info in pt_anno_list[i]:
                            info['plv'] = (plv:=info['plv']+val)
                            toks = (pin:=info['ce'].pin).split('/')
                            if len(toks) > plv:
                                pin = ""
                                for i in range(-1, -1-plv, -1):
                                    pin = "/{}".format(toks[i]) + pin
                                pin = '...' + pin
                            toks = anno.get_text().split('\n')
                            anno.set_text(
                                    f"pin: {pin}\n{toks[-2]}\n{toks[-1]}")
                    plt.draw()
                case 'BT':
                    for i in range(len(pt_anno_list)):
                        for pt, anno, info in pt_anno_list[i]:
                            toks = anno.get_text().split('\n')
                            if val == 2 and info['ct'] is False:
                                toks[0] = "{}\nlib: {}".format(
                                            toks[0], info['ce'].cell)
                            anno.set_text(f"{toks[0]}\n{toks[-2]}\n{toks[-1]}")
                    plt.draw()
                case 'RESET':
                    for i in range(len(pt_anno_list)):
                        for pt, anno, info in pt_anno_list[i]:
                            if anno._x == -0.5 and info['dy_rt'] == 0.5:
                                info['plv'] = 2
                                toks = (pin:=info['ce'].pin).split('/')
                                if len(toks) > 2:
                                    pin = f'.../{toks[-2]}/{toks[-1]}'
                                toks = anno.get_text().split('\n')
                                anno.set_text(
                                        f"pin: {pin}\n{toks[-2]}\n{toks[-1]}")
                            info['dy_rt'] = 0.5
                            anno.set_x(-0.5)
                            anno.set_y(info['min_dy']
                                       + info['dy_off']*info['dy_rt'])
                    plt.draw()

        # fig.canvas.mpl_connect('motion_notify_event', on_move)
        fig.canvas.mpl_connect('button_press_event', on_mouse)
        fig.canvas.mpl_connect('key_press_event', on_key)
        plt.show()


def get_time_bar_info(cmp_id: str, default_tag: str, seg_dict: None, 
                      bar_ptype: set, path: TimePath, is_order=False):
    """Get the time bar information."""
    pal_cnt = len(Palette.hist)
    hist_palette = {}
    if seg_dict is not None and is_order:
        for i, key in enumerate(seg_dict.keys()):
            hist_palette[key] = Palette.hist[i%pal_cnt]
    else:
        for i in range(pal_cnt):
            hist_palette[i] = Palette.hist[i]

    if seg_dict is None:
        default_color = Palette.hist[0]
        init_tag = None
    else:
        default_color = Palette.hist_default 
        init_tag = default_tag if default_tag in seg_dict else None

    bar_lg, spin_pos = [], (None, None)
    lv_ce, lv_c, lv_ha, lv_ec = [], [], [], []

    for type_ in ('l', 'c', 'd'):
        if type_ in bar_ptype:
            tag, pal_idx = init_tag, -1
            bar_lg_path = ({default_tag: default_color} if init_tag is None 
                           else {})
            lv_ce_path, lv_c_path, lv_ha_path, lv_ec_path  = [], [], [], []
            s_path = path.cpath if type_ == 'c' else path.lpath
            for cid, cell in enumerate(s_path):
                if seg_dict is None:
                    pass
                elif tag is None:
                    new_tag = init_tag 
                    for key, ps_re in seg_dict.items():
                        if (m:=ps_re.fullmatch(cell[cmp_id])):
                            new_tag = key
                            break
                    tag = new_tag
                elif seg_dict[tag].fullmatch(cell[cmp_id]) is None:
                    new_tag = init_tag
                    for key, ps_re in seg_dict.items():
                        if (m:=ps_re.fullmatch(cell[cmp_id])):
                            new_tag = key
                            break
                    tag = new_tag

                if cid == path.spin and type_ == 'd' and 'f' not in bar_ptype:
                    pal_idx = -1
                    bar_lg_path = (
                        {default_tag: default_color} if init_tag is None 
                        else {})
                    lv_ce_path, lv_c_path = [], []
                    lv_ha_path, lv_ec_path = [], []

                key = default_tag if tag is None else tag
                if key not in bar_lg_path:
                    if is_order:
                        bar_lg_path[key] = hist_palette[key]
                    else:
                        pal_idx += 1
                        bar_lg_path[key] = hist_palette[pal_idx%pal_cnt]

                lv_ce_path.append(cell)
                lv_c_path.append(bar_lg_path[key])
                if cid == path.spin and type_ == 'd':
                    spin_pos = (len(lv_ha), len(lv_ha_path))
                    lv_ha_path.append('/')
                    lv_ec_path.append('b')
                else:
                    lv_ha_path.append('')
                    lv_ec_path.append('k')

            if seg_dict is not None and is_order:
                m_bar_lg_path = {default_tag: default_color}
                for key in seg_dict.keys():
                    if key in bar_lg_path:
                        m_bar_lg_path[key] = bar_lg_path[key]
            else:
                m_bar_lg_path = bar_lg_path

            bar_lg.append(m_bar_lg_path)
            lv_ce.append(lv_ce_path)
            lv_c.append(lv_c_path)
            lv_ha.append(lv_ha_path)
            lv_ec.append(lv_ec_path)

    return (bar_lg, lv_ce, lv_c, lv_ha, lv_ec), spin_pos


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
        description="PrimeTime Report Analysis\n" + 
                    "  -- Timing Path Summary\n" +
                    "  -- command: report_timing")

    parser.add_argument('-version', action='version', version=VERSION)
    parser.add_argument('rpt_fp', help="report_path") 
    parser.add_argument('-c', dest='cfg_fp', metavar='<config>', 
                            help="set the config file path") 
    parser.add_argument('-nc', dest='is_nocfg', action='store_true', 
                            help="disable to load the config file")
    parser.add_argument('-r', dest='range', metavar='<value>', 
                            help="report scan range select,\n" + 
                                 "ex: 6,16+2,26:100,26:100+2\n" +
                                 "(default load 1 path from line 0)") 
    parser.add_argument('-ckc', dest='ckc_en', action='store_true', 
                            help="enable clock path check")
    parser.add_argument('-ckcd', dest='ckc_dump', action='store_true', 
                            help="dump clock path check contents to the file")
    parser.add_argument('-dts', dest='dts_en', action='store_true', 
                            help="enable clock/data path delta summation")
    parser.add_argument('-seg', dest='seg_en', action='store_true', 
                            help="enable path segment")
    parser.add_argument('-bar', dest='bar', metavar='<pat>', nargs='*', 
                            choices=['p','c','t','d','i', 'ct'],
                            help="bar view data type select\n" +
                                 "(p:distance, c:cap, t:tran, d:delta, i:incr, ct:cell_type)") 
    parser.add_argument('-barp', dest='bar_ptype', metavar='<pat>', nargs='*', 
                            choices=['f','d','l','c'],
                            help="bar view path type select\n" +
                                 "(f:full data, d:data, l:launch clk, c:capture clk)") 
    parser.add_argument('-bars', dest='bars', metavar='<tag>', 
                            help="bar view data type set defined in the config file") 
    parser.add_argument('-barr', dest='bar_rev', action='store_true', 
                            help="axis reverse for bar view")
    parser.add_argument('-debug', dest='is_debug', action='store_true', 
                            help="enable debug mode")
    return parser


def main():
    """Main Function"""
    parser = create_argparse()
    args = parser.parse_args()
    default_cfg = ".pt_ana_ts.setup"

    if args.is_nocfg:
        args.cfg_fp = None
    elif args.cfg_fp is None and os.path.exists(default_cfg):
        if os.path.isfile(default_cfg):
            args.cfg_fp = default_cfg

    range_list = []
    if args.range is not None:
        range_re = re.compile(r"(?P<st>\d+)(?::(?P<ed>\d+))?(?:\+(?P<nu>\d+))?")
        for range_ in args.range.split(','):
            if (m:=range_re.fullmatch(range_)):
                st = int(m.group('st'))
                ed = None if (ed:=m.group('ed')) is None else int(ed)
                nu = None if (nu:=m.group('nu')) is None else int(nu)
                range_list.append([st, ed, nu])
    if not range_list:
        range_list.append([0, None, 1])  # [start_line, last_line, path_count]
    
    print("\n Report: {}\n".format(os.path.abspath(args.rpt_fp)))
    report_summary(args, range_list)


if __name__ == '__main__':
    main()


