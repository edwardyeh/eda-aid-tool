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

from .utils.common import PKG_VERSION 

VERSION = f"pt_ana_ts version 1.0.0 ({PKG_VERSION})"

### Global Variable ###    {{{

prange_re1 = re.compile(r"(\d+)\+(\d+)")
prange_re2 = re.compile(r"(\d+)-(\d+)")
path_re = re.compile(r"\s*\S+")

TIME_COL_NUM = 12
LN, PT, CELL, PHY, FO, CAP, DTRAN, TRAN, DERATE, DELTA, INCR, PATH = range(TIME_COL_NUM)
col_dict = {'net': FO, 'cap': CAP, 'dtran': DTRAN, 'tran': TRAN, 'derate': DERATE, 'delta': DELTA}
ANNO_SYM = set(['H', '^', '*', '&', '$', '+', '@'])

# clock pin
CKP = set(['CP', 'CPN'])    # TSMC
CKP.add('CK')               # SYNP virage

# Histogram
HIST_DEFAULT_COLOR = "#caccd1"
HIST_PALETTE = [
    "#84bd00", "#efdf00", "#fe5000", "#e4002b", 
    "#da1884", "#a51890", "#0077c8", "#008eaa", 
    "#74d2e7", "#48a9c5", "#0085ad", "#8db9ca", 
    "#4298b5", "#005670", "#004182", "#44712e",
    "#915907", "#b24020", "#dce6f1", "#d7ebce",
    "#fce2ba", "#fadfd8", "#0a66c2", "#83941f",
    "#e7a33e", "#f5987e",
]

#}}}

### Function ###

def report_time_summary(args, prange_list: list):
    """Detial Time Path Analysis"""  #{{{
    cons_cfg = load_times_cfg(args.cfg_fp)
    time_rpt_dict = parse_time_rpt(args.rpt_fp, prange_list, cons_cfg)

    if args.is_debug:
        print("opt: {}".format(time_rpt_dict['opt']))
        for path in time_rpt_dict['path']:
            for key, val in path.items():
                if key == 'lpath':
                    lpath = val
                elif key == 'cpath':
                    cpath = val
                else:
                    print("{}: {}".format(key, val))
            if 'lpath' in locals():
                for i, cell in enumerate(lpath):
                    print("lpath{}: {}".format(i, cell))
            if 'cpath' in locals():
                for i, cell in enumerate(cpath):
                    print("cpath{}: {}".format(i, cell))
    else:
        for pid, path in enumerate(time_rpt_dict['path']):
            splen = len(stp:=path['lpath'][path['spin']][PT])
            if (plen:=len(edp:=path['lpath'][-1][PT])) < splen:
                plen = splen

            idly = path['idly'] if 'idly' in path else 0.0

            ## path information
            print(" {}".format("=" * 60))
            if plen > 80:
                print(" Startpoint: {}".format(stp))
                print("             ({} {})".format(path['sed'], path['sck']))
                print(" Endpoint:   {}".format(edp))
                print("             ({} {})".format(path['eed'], path['eck']))
            else:
                print(" Startpoint: {} ({} {})".format(stp.ljust(plen), path['sed'], path['sck']))
                print(" Endpoint:   {} ({} {})".format(edp.ljust(plen), path['eed'], path['eck']))
            print(" Path group: {}".format(path['grp']))
            print(" Delay type: {}".format(path['type']))
            print(" {}".format("=" * 60))

            ## path latency
            print(" {:26}{: 5.4f}".format("data latency:", path['arr']-idly-path['slat']-path['sev']))
            print(" {:26}{: 5.4f}".format("arrival:", path['arr']))
            print(" {:26}{: 5.4f}".format("required:", path['req']))
            print(" {:26}{: 5.4f}".format("slack:", path['slk']))
            if 'idly' in path or 'odly' in path or len(path['cdh']) != 0:
                print(" {}".format("-" * 60))
            if 'idly' in path:
                print(" {:26}{: 5.4f}".format("input delay:", idly))
            if 'odly' in path:
                print(" {:26}{: 5.4f}".format("output delay:", abs(path['odly'])))
            for tag, val in path['cdh']:
                print(" {}{: 5.4f}".format(f"{tag}:".ljust(26), val))
            print(" {}".format("=" * 60))

            ## clock latency & check
            print(" {:26}{: 5.4f}".format("launch clock edge value:", path['sev']))
            print(" {:26}{: 5.4f}".format("capture clock edge value:", path['eev']))
            print(" {:26}{: 5.4f}".format("launch clock latency:", path['slat']))
            print(" {:26}{: 5.4f}".format("capture clock latency:", path['elat']))
            print(" {:26}{: 5.4f}".format("crpr:", path['crpr']))
            print(" {:26}{: 5.4f}".format("clock skew:", path['slat'] - path['elat'] - path['crpr']))

            if args.ckc_en or cons_cfg['ckc_en']:
                if 'sgpi' in path:
                    sgpi = path['sgpi'] + 1
                    sgpath, spath = path['lpath'][0:sgpi], path['lpath'][sgpi:path['spin']+1]
                else:
                    sgpath, spath = [], path['lpath'][0:path['spin']+1]

                if 'egpi' in path:
                    egpi = path['egpi'] + 1
                    egpath, epath = path['cpath'][0:egpi], path['cpath'][egpi:path['spin']+1]
                else:
                    egpath, epath = [], path['cpath']

                gcc_rslt, scc_rslt, ctc_rslt = clock_path_check(sgpath, spath, egpath, epath, 
                                                pid=pid, cons_cfg=cons_cfg, is_dump=args.ckc_dump)
                
                col_sz = len(split_lv:=f"{len(spath)}/{len(epath)}/{scc_rslt[0]}")
                print(" {}".format("-" * 60))
                print(" {:26} {}    {}".format("clock cell type check:", 
                                                ctc_rslt[0].ljust(col_sz), ctc_rslt[1]))
                print(" {:26} {}    {}".format("clock source path match:", 
                                                gcc_rslt[0].ljust(col_sz), gcc_rslt[1]))
                print(" {:26} {}    (ln:{}:{})".format("clock network path fork:", 
                                                split_lv, *scc_rslt[1:]))

            print(" {}".format("=" * 60))

            ## clock & path delta
            if args.dts_en or cons_cfg['dts_en']:
                ddt_val = "{: 5.4f}".format(path['ddt']) if 'ddt' in path else ' N/A'
                sdt_val = "{:5.4f}".format(path['sdt']) if 'sdt' in path else 'N/A'
                edt_val = "{:5.4f}".format(path['edt']) if 'edt' in path else 'N/A'
                print(" {:26}{} : {} : {}".format("total delta (D:L:C):", ddt_val, sdt_val, edt_val))
                print(" {}".format("=" * 60))

            ## path segment
            if 'pc' in cons_cfg and (args.seg_en or cons_cfg['seg_en']):
                show_path_segment(path, time_rpt_dict['opt'], cons_cfg)
            print()

        ## show time bar chart
        bar_dtype = set()
        if args.bars is not None:
            if 'bds' in cons_cfg and args.bars in cons_cfg['bds']:
                bar_dtype |= set(cons_cfg['bds'][args.bars])
            else:
                print(" [WARNING] The bars option cannot find in the configuration, ignore.\n")
        if args.bar is not None:
            bar_dtype |= set(args.bar) if len(args.bar) != 0 else set(['p','c','t','d','i','ct'])
        if 'ct' in bar_dtype:
            bar_dtype.add('i')

        if len(bar_dtype) != 0:
            if args.bar_ptype is None or len(args.bar_ptype) == 0:
                bar_ptype = set(['f', 'd'])
            else:
                bar_ptype = set(args.bar_ptype)
                if 'f' in bar_ptype:
                    bar_ptype.add('d')

            show_time_bar(time_rpt_dict['path'][0], time_rpt_dict['opt'], cons_cfg, 
                          bar_dtype, bar_ptype, args.bar_rev)
#}}}

def load_times_cfg(cfg_fp) -> dict:
    """Load Configuration for TimeS Mode"""  #{{{
    cons_cfg = {'ckc_en': False, 'dts_en': False, 'seg_en': False, 'ckm_nock': False}
    if cfg_fp is None:
        return cons_cfg

    with open(cfg_fp, 'r') as f:
        for no, line in enumerate(f.readlines(), start=1):
            line = line.split('#')[0].strip()
            if line != "":
                try:
                    if line.startswith('clock_check_default_on:'):
                        enable = line.split()[-1].lower()
                        cons_cfg['ckc_en'] = True if enable == 'true' else False
                    elif line.startswith('delta_sum_default_on:'):
                        enable = line.split()[-1].lower()
                        cons_cfg['dts_en'] = True if enable == 'true' else False
                    elif line.startswith('path_segment_default_on:'):
                        enable = line.split()[-1].lower()
                        cons_cfg['seg_en'] = True if enable == 'true' else False
                    elif line.startswith('ckm_with_non_clock_cell:'):
                        enable = line.split()[-1].lower()
                        cons_cfg['ckm_nock'] = True if enable == 'true' else False
                    elif line.startswith('bds:'):
                        tag, *pat = line[4:].split()
                        cons_cfg.setdefault('bds', {})[tag] = pat
                    elif line.startswith('ckt:'):
                        tag, pat = line[4:].split()
                        match tag.lower():
                            case 'y': tag = True
                            case 'n': tag = False
                            case  _ : raise SyntaxError
                        cons_cfg.setdefault('ckt', []).append((tag, re.compile(pat)))
                    elif line.startswith('ckp:'):
                        pat = line[4:].split()[0]
                        cons_cfg.setdefault('ckp', set()).add(pat)
                    elif line.startswith('ckm:'):
                        pat = re.compile(line[4:].split()[0])
                        cons_cfg.setdefault('ckm', []).append(pat)
                    elif line.startswith('pc:'):
                        tag, pat = line[3:].split()
                        cons_cfg.setdefault('pc', {})[tag] = re.compile(pat)
                    elif line.startswith('cc:'):
                        tag, pat = line[3:].split()
                        cons_cfg.setdefault('cc', {})[tag] = re.compile(pat)
                    elif line.startswith('cdh:'):
                        toks = line[4:].split('"') 
                        if len(toks) > 1:
                            ctype, pi, po, tag = *toks[0].split(), toks[1]
                        else:
                            ctype, pi, po, tag = toks[0].split()
                        cdh_dict = cons_cfg.setdefault('cdh', {})
                        cdh_pair = cdh_dict.setdefault(ctype, {})
                        cdh_pair[f"{pi}:{po}"] = tag
                except SyntaxError:
                    raise SyntaxError(f"config syntax error (ln:{no})")

    return cons_cfg
#}}}

def parse_time_rpt(rpt_fp, prange_list: list, cons_cfg: dict) -> dict:
    """Parsing Timing Report"""  #{{{
    if os.path.splitext(rpt_fp)[1] == '.gz':
        fp = gzip.open(rpt_fp, mode='rt')
    else:
        fp = open(rpt_fp)

    no, opt_set = get_time_opt_set(fp)
    ckp_set = cons_cfg['ckp'] if 'ckp' in cons_cfg else set()
    cdh_dict = cons_cfg['cdh'] if 'cdh' in cons_cfg else {}
    time_rpt_dict = {'opt': opt_set, 'path': []}

    for prange in prange_list:
        rec_cnt, is_ongo = 0, True
        p_st = prange[0] - 1
        while no < p_st:
            line, no = fp.readline(), no + 1

        while is_ongo:
            no, path, is_eof = get_time_path(fp, no, opt_set, ckp_set, cdh_dict)
            if is_eof:
                break
            else:
                rec_cnt += 1
            if path is not None:
                time_rpt_dict['path'].append(path)
            if prange[1] is not None and no >= prange[1]:
                is_ongo = False
            elif prange[2] is not None and rec_cnt == prange[2]:
                is_ongo = False

    fp.close()
    return time_rpt_dict
#}}}

def get_time_opt_set(fp) -> tuple:
    """Get Option Set"""  #{{{
    # return: file_no:int, option:set
    is_ongo, opt_set = False, set()
    line, no = fp.readline(), 1

    while line != "":
        line = line.strip()
        if is_ongo:
            toks = line.split()
            if toks[0][0] == '*':
                break
            elif toks[0] == '-path_type':
                if toks[1] == 'full':
                    opt_set.add('pf')
                elif toks[1] == 'full_clock':
                    opt_set.add('pfc')
                elif toks[1] == 'full_clock_expanded':
                    opt_set.add('pfce')
            elif toks[0] == '-input_pins':
                opt_set.add('input')
            elif toks[0] == '-nets':
                opt_set.add('net')
            elif toks[0] == '-transition_time':
                opt_set.add('tran')
            elif toks[0] == '-capacitance':
                opt_set.add('cap')
            elif toks[0] == '-show_delta' or toks[0] == '-crosstalk_delta':
                opt_set.add('delta')
            elif toks[0] == '-derate':
                opt_set.add('derate')
        elif line[:6] == "Report":
            is_ongo = True
        line, no = fp.readline(), no+1

    if 'tran' in opt_set and 'delta' in opt_set:
        opt_set.add('dtran')

    return no, opt_set
#}}}

def get_time_path(fp, no: int, opt_set: set, ckp_set: set, cdh_dict: None) -> tuple:
    """Parsing Timing Path"""  #{{{
    STD, PREF, LPATH, CPATH, FINAL = range(5)
    time_path, state, p_state = None, STD, 0
    is_eof, line, no = False, fp.readline(), no + 1
    cdh_result = []

    if line == '':
        is_eof = True

    while line != '':
        if state == LPATH or state == CPATH:
            toks = path_re.findall(line)
        else:
            toks = line.strip().split()
        # print("toks:", toks)          # debug
        # import pdb; pdb.set_trace()   # debug

        if len(toks) == 0:
            pass

        elif state == STD and toks[0] == 'Startpoint:':
            state = PREF
            time_path = {'stp': toks[1], 'lpath': [], 'cpath': [], 'cdh': []}

        elif state == PREF:
            if toks[0][0] == '-':
                state, add_ckp, spin, sdt, ddt = LPATH, False, None, 0, 0
                pv_path = [None, 'None', 'None'] + [0] * (TIME_COL_NUM - 2)
            elif toks[0] == 'Endpoint:':
                time_path['edp'] = toks[1]
            elif toks[1] == 'Group:':
                time_path['grp'] = toks[2]
            elif toks[1] == 'Type:':
                time_path['type'] = toks[2]
            elif toks[0] == 'Point':
                path_cols = path_re.findall(line)

        elif state == LPATH:
            # import pdb; pdb.set_trace()   # debug
            tag0, tag1 = toks[0].lstrip(), toks[1].lstrip()
            if tag1 == 'arrival':
                # import pdb; pdb.set_trace()   # debug
                state, p_state, edt = CPATH, 0, 0
                time_path['arr'] = float(toks[-1])
                if spin is None:
                    time_path['spin'] = 0
                    print(" [WARNING] Cannot detect the startpoint, use 1st cell pin default.\n")
                else:
                    time_path['spin'] = spin
                time_path['slat'] = time_path['lpath'][time_path['spin']][PATH] - time_path['sev']
                if 'idly' in time_path:
                    time_path['slat'] -= time_path['idly']
                if 'delta' in opt_set:
                    if 'pf' in opt_set:
                        time_path['ddt'] = ddt
                    else:
                        time_path['sdt'] = sdt
                        time_path['ddt'] = ddt - sdt

            elif tag1 == 'external':
                time_path['idly'] = float(toks[-3])
                add_ckp = True

            elif p_state == 0 and tag0 == 'clock':
                time_path['sck'] = tag1
                time_path['sed'] = toks[2].lstrip()[1:]
                if len(toks) == 4:
                    toks, no = fp.readline().strip().split(), no + 1
                time_path['sev'] = float(toks[-2])
                p_state = 1

            elif p_state == 1 and tag0 == 'clock':
                if len(toks) == 4:
                    toks, no = fp.readline().strip().split(), no + 1
                time_path['sslat'] = float(toks[-2])
                p_state = 2

            elif p_state == 2:
                # import pdb; pdb.set_trace()   # debug
                path = [no, None, None] + [0] * (TIME_COL_NUM - 2)
                toks_len = len(toks)
                if (toks_len == 2) or \
                   (toks_len == 3 and toks[2].endswith('<-')) or \
                   (toks_len == 4 and toks[2].endswith('(gclock')):
                    toks2, no = path_re.findall(fp.readline()), no + 1
                    start_col = 0
                else:
                    toks2 = toks
                    if (tag2:=toks[2].lstrip()) == '<-':
                        start_col = 3
                    elif tag2 == '(gclock':
                        start_col = 4
                    else:
                        start_col = 2

                if tag1 == '(net)':
                    get_time_cell(opt_set, path_cols, toks2, time_path['lpath'][-1], start_col)
                    # print("path (l-net):", time_path['lpath'][-1])  # debug
                else:
                    path[PT], path[CELL] = tag0, tag1[1:-1]
                    get_time_cell(opt_set, path_cols, toks2, path, start_col)
                    ddt += path[DELTA]
                    if toks_len > 2 and toks[2].endswith('(gclock'):
                        spin, sdt = len(time_path['lpath']), ddt
                        time_path['sgpi'] = spin
                    elif path[PT].split('/')[-1] in CKP:
                        spin, sdt = len(time_path['lpath']), ddt
                    elif path[PT] in ckp_set:
                        spin, sdt = len(time_path['lpath']), ddt
                    elif add_ckp:
                        spin, sdt = len(time_path['lpath']), ddt
                        add_ckp = False
                    time_path['lpath'].append(path)
                    if cdh_dict is not None and pv_path[CELL] in cdh_dict:
                        cdh_pair = "{}:{}".format(pv_path[PT].split('/')[-1], path[PT].split('/')[-1])
                        if (ctype:=path[CELL]) in cdh_dict and cdh_pair in cdh_dict[ctype]:
                            time_path['cdh'].append((cdh_dict[ctype][cdh_pair], path[INCR]))
                    pv_path = path
                    # print("path (l-nor):", path)  # debug

        elif state == CPATH:
            # import pdb; pdb.set_trace()   # debug
            tag0, tag1 = toks[0].lstrip(), toks[1].lstrip()
            if tag1 == 'required':
                # import pdb; pdb.set_trace()   # debug
                state = FINAL
                time_path['req'] = float(toks[-1])
                time_path['elat'] = time_path['req'] - time_path['eev'] - \
                                    time_path['crpr'] - time_path['unc'] - \
                                    odly - gate_dly - lib_dly
                if 'delta' in opt_set and 'pf' not in opt_set:
                    time_path['edt'] = edt

            elif tag1 == 'reconvergence':
                time_path['crpr'] = float(toks[-2])
            elif tag1 == 'uncertainty':
                time_path['unc'] = float(toks[-2])
            elif tag1 == 'external':
                time_path['odly'] = (odly:=float(toks[-2]))
            elif tag1 == 'setup' or tag1 == 'hold':
                time_path['lib'] = (lib_dly:=float(toks[-2]))
            elif tag1 == 'gating':
                time_path['gate'] = (gate_dly:=float(toks[-2]))

            elif p_state == 0 and tag0 == 'clock':
                # default zero
                odly, lib_dly, gate_dly = 0.0, 0.0, 0.0
                time_path['crpr'] = 0.0
                time_path['unc']  = 0.0
                time_path['eck'] = tag1
                time_path['eed'] = toks[2].lstrip()[1:]
                if len(toks) == 4:
                    toks, no = fp.readline().strip().split(), no + 1
                time_path['eev'] = float(toks[-2])
                p_state = 1

            elif p_state == 1 and tag0 == 'clock':
                if len(toks) == 4:
                    toks, no = fp.readline().strip().split(), no + 1
                time_path['eslat'] = float(toks[-2])
                p_state = 2

            elif p_state == 2:
                # import pdb; pdb.set_trace()   # debug
                path = [no, None, None] + [0] * (TIME_COL_NUM - 2)
                toks_len = len(toks)
                if (toks_len == 2) or \
                   (toks_len == 4 and toks[2].endswith('(gclock')):
                    toks2, no = path_re.findall(fp.readline()), no + 1
                    start_col = 0
                else:
                    toks2 = toks
                    if toks[2].endswith('(gclock'):
                        start_col = 4
                    else:
                        start_col = 2

                if tag1 == '(net)':
                    get_time_cell(opt_set, path_cols, toks2, time_path['cpath'][-1], start_col)
                    # print("path (c-net):", time_path['cpath'][-1])  # debug
                else:
                    path[PT], path[CELL] = tag0, tag1[1:-1]
                    get_time_cell(opt_set, path_cols, toks2, path, start_col)
                    edt += path[DELTA]
                    if toks_len > 2 and toks[2].endswith('(gclock'):
                        time_path['egpi'] = len(time_path['cpath'])
                    time_path['cpath'].append(path)
                    # print("path (c-nor):", path)  # debug

        elif state == FINAL:
            # import pdb; pdb.set_trace()   # debug
            if toks[0] == 'slack':
                time_path['slk'] = float(toks[2])
                break

        line, no = fp.readline(), no + 1
    
    return no, time_path, is_eof
#}}}

def get_time_cell(opt_set: set, path_cols: list, toks: list, path: list, start_col: int):
    """Get Time Cell"""  #{{{
    cid = start_col
    cpos = sum([len(toks[i]) for i in range(cid+1)])

    try:
        ## fanout, cap, dtran, tran, derate, delta
        tid, tpos = 0, len(path_cols[0])
        for attr, pid in col_dict.items():
            if attr in opt_set:
                tpos += len(path_cols[tid:=tid+1])
                # import pdb; pdb.set_trace()
                if tpos >= cpos:
                    path[pid] = int(toks[cid]) if attr == 'net' else float(toks[cid])
                    cpos += len(toks[cid:=cid+1])

        ## incr, path, location
        path[INCR], cid = float(toks[cid]), cid+1
        if toks[cid][-1] in ANNO_SYM:
            cid += 1
        path[PATH], cid = float(toks[cid]), cid+1
        if toks[cid][-1] == 'r' or toks[cid][-1] == 'f':
            cid += 1
        if 'phy' in opt_set:
            path[PHY] = [int(x) for x in toks[cid].lstrip()[1:-1].split(',')]
    except IndexError:
        pass
    except ValueError:
        pass
    # import pdb; pdb.set_trace()
#}}}

def clock_path_check(sgpath: list, spath: list, egpath: list, epath: list, 
                     pid: int=0, cons_cfg: dict=None, is_dump: bool=False):
    """Clock Path Similarity Check"""  #{{{
    ## return: gcc_rslt: list[0:2], scc_rslt: list[0:4], ctc_rslt: list[0:2] 

    ## gclock path match check
    gcc_rslt, fail_by_ckm, gclist = ['PASS', ''], True, []
    sglen, eglen, pvckm_re = len(sgpath), len(egpath), None
    egset = set([ecell[PT] for ecell in egpath])
    empty_cell = ("", "", "")   # (LN, PT, CELL)
    same_ckm_cell = ("", "... same clock module ...", "")

    ckt_list = cons_cfg['ckt'] if (cons_cfg is not None and 'ckt' in cons_cfg) else []
    ckm_list = cons_cfg['ckm'] if (cons_cfg is not None and 'ckm' in cons_cfg) else []

    if sglen != 0 and eglen != 0:
        scell, ecell, si, ei = sgpath[0], egpath[0], 1, 1
        while True:
            if scell[PT] == ecell[PT]:
                gclist.append((scell, ecell))
                match (si==sglen, ei==eglen):
                    case (False, False):
                        scell, ecell, si, ei = sgpath[si], egpath[ei], si+1, ei+1
                    case (False, True):
                        gcc_rslt[0], fail_by_ckm = 'FAIL', False
                        for i in range(si, sglen):
                            gclist.append((sgpath[i], empty_cell))
                        break
                    case (True, False):
                        gcc_rslt[0], fail_by_ckm = 'FAIL', False
                        for i in range(ei, eglen):
                            gclist.append((empty_cell, egpath[i]))
                        break
                    case (True, True):
                        break
            else:
                gcc_rslt[0], sckm, eckm = 'FAIL', False, False
                if pvckm_re is not None:
                    ckm_list2 = [pvckm_re] + ckm_list
                else:
                    ckm_list2 = ckm_list

                for ckm_re in ckm_list2:
                    sckm = True if ckm_re.fullmatch(scell[PT]) else False
                    eckm = True if ckm_re.fullmatch(ecell[PT]) else False
                    if sckm and eckm:
                        pvckm_re = ckm_re
                        break
                if not (all_ckm := sckm and eckm):
                    pvckm_re = None
                fail_by_ckm &= all_ckm

                dummy_cell = same_ckm_cell if all_ckm else empty_cell
                if scell[PT] in egset:
                    gclist.append((dummy_cell, ecell))
                    ecell, ei = egpath[ei], ei+1
                else:
                    gclist.append((scell, dummy_cell))
                    scell, si = sgpath[si], si+1

        if gcc_rslt[0] == 'FAIL' and fail_by_ckm:
            gcc_rslt[1] = "(caused by user-defined clk modules)"
    else:
        gcc_rslt[0] = 'N/A'

    ## sclock path match check
    slen, elen = len(spath), len(epath)
    scc_rslt = (-1, 'N/A', 'N/A')    # (split_level, lineNo_in_spath, lineNo_in_epath)
    if slen != 0 and spath[-1][CELL] in ('inout', 'in'):
        del spath[-1]
        slen -= 1

    if slen != 0 and elen != 0:
        scell, ecell, si, ei = spath[0], epath[0], 1, 1
        while True:
            if scell[PT] != ecell[PT]:
                break
            else:
                scc_rslt = (scc_rslt[0]+1, scell[LN], ecell[LN])
                if si == slen or ei == elen:
                    break
                else:
                    scell, ecell, si, ei = spath[si], epath[ei], si+1, ei+1

    ## cell type check
    ctc_pass, fail_by_ckm, ctc_rslt, gct_list = True, cons_cfg['ckm_nock'], None, []
    sct_list, ect_list = [], []

    if len(ckt_list):
        pvckm_re = None
        # gclock path cell type check
        for i in range(len(gclist)):
            sc_pass = ec_pass = False
            sname, ename = gclist[i][0][CELL], gclist[i][1][CELL]
            for ckt_en, ckt_re in ckt_list:
                if not sc_pass:
                    if sname == "":
                        sc_pass = True
                    elif ckt_re.fullmatch(sname):
                        sc_pass = ckt_en
                if not ec_pass:
                    if ename == "":
                        ec_pass = True
                    elif ckt_re.fullmatch(ename):
                        ec_pass = ckt_en
                if sc_pass and ec_pass:
                    break
            ctc_pass &= (cur_pass := sc_pass and ec_pass)

            sc_is_ckm, ec_is_ckm = sc_pass, ec_pass
            if not cur_pass and cons_cfg['ckm_nock']:
                sname, ename = gclist[i][0][PT], gclist[i][1][PT]
                if pvckm_re is not None:
                    ckm_list2 = [pvckm_re] + ckm_list
                else:
                    ckm_list2 = ckm_list

                for ckm_re in ckm_list2:
                    sc_is_ckm = sc_is_ckm or (True if ckm_re.fullmatch(sname) else False)
                    ec_is_ckm = ec_is_ckm or (True if ckm_re.fullmatch(ename) else False)
                    if sc_is_ckm and ec_is_ckm:
                        pvckm_re = ckm_re
                        break

                if not (all_ckm := sc_is_ckm and ec_is_ckm):
                    pvckm_re = None
                fail_by_ckm &= all_ckm

            gct_list.append(('' if sc_pass else 'IG' if sc_is_ckm else 'FA', 
                             '' if ec_pass else 'IG' if ec_is_ckm else 'FA'))

        # launch path cell type check
        for cell in spath:
            sc_pass = False
            for ckt_en, ckt_re in ckt_list:
                if ckt_re.fullmatch(cell[CELL]):
                    sc_pass = ckt_en
                    break
            ctc_pass &= sc_pass

            sc_is_ckm = False
            if not sc_pass and cons_cfg['ckm_nock']:
                if pvckm_re is not None:
                    ckm_list2 = [pvckm_re] + ckm_list
                else:
                    ckm_list2 = ckm_list

                for ckm_re in ckm_list2:
                    if (sc_is_ckm := True if ckm_re.fullmatch(cell[PT]) else False):
                        pvckm_re = ckm_re
                        break

                if not sc_is_ckm:
                    pvckm_re = None
                fail_by_ckm &= sc_is_ckm

            sct_list.append((cell, '' if sc_pass else 'IG' if sc_is_ckm else 'FA'))

        # capture path cell type check
        for cell in epath:
            ec_pass = False
            for ckt_en, ckt_re in ckt_list:
                if ckt_re.fullmatch(cell[CELL]):
                    ec_pass = ckt_en
                    break
            ctc_pass &= ec_pass

            ec_is_ckm = False
            if not ec_pass and cons_cfg['ckm_nock']:
                if pvckm_re is not None:
                    ckm_list2 = [pvckm_re] + ckm_list
                else:
                    ckm_list2 = ckm_list

                for ckm_re in ckm_list2:
                    if (ec_is_ckm := True if ckm_re.fullmatch(cell[PT]) else False):
                        pvckm_re = ckm_re
                        break

                if not ec_is_ckm:
                    pvckm_re = None
                fail_by_ckm &= ec_is_ckm

            ect_list.append((cell, '' if ec_pass else 'IG' if ec_is_ckm else 'FA'))

        ctc_rslt = ['PASS' if ctc_pass else 'FAIL']
        if not ctc_pass and fail_by_ckm:
            ctc_rslt.append("(caused by user-defined clk modules)")
        else:
            ctc_rslt.append("")
    else:
        ctc_rslt = ['N/A', '']
        gct_list = [('--', '--') for i in range(len(gclist))]

    ## dump gclock compare list
    if is_dump:
        gc_col_sz, sc_col_sz, ec_col_sz = [0, 0, 0], [0, 0, 0], [0, 0, 0]

        for i in range(len(gclist)):
            for cid in range(LN, CELL+1):
                if (len_:=len(str(gclist[i][0][cid]))) > gc_col_sz[cid]:
                    gc_col_sz[cid] = len_
                if (len_:=len(str(gclist[i][1][cid]))) > gc_col_sz[cid]:
                    gc_col_sz[cid] = len_

        for cell in spath:
            for cid in range(LN, CELL+1):
                if (len_:=len(str(cell[cid]))) > sc_col_sz[cid]:
                    sc_col_sz[cid] = len_

        for cell in epath:
            for cid in range(LN, CELL+1):
                if (len_:=len(str(cell[cid]))) > ec_col_sz[cid]:
                    ec_col_sz[cid] = len_

        for i, sz in enumerate([4, 10, 10], start=LN):
            gc_col_sz[i] = sz if gc_col_sz[i] < sz else gc_col_sz[i]
            sc_col_sz[i] = (sz if sc_col_sz[i] < sz else sc_col_sz[i])
            ec_col_sz[i] = (sz if ec_col_sz[i] < sz else ec_col_sz[i])

        with open(f"clock_check{pid}.dump", "w") as f:
            f.write("\n=== GClock Compare:\n")
            f.write("+-{}-+-{}-+-{}-+-{}----+-{}----+\n".format(
                        '-' * 4, 
                        '-' * 2,
                        '-' * gc_col_sz[LN],
                        '-' * gc_col_sz[PT],
                        '-' * gc_col_sz[CELL]))
            f.write("| {} | {} | {} | {}    | {}    |\n".format(
                        'Type'.center(4), 
                        'CK'.ljust(2), 
                        'Line'.ljust(gc_col_sz[LN]), 
                        'Pin'.ljust(gc_col_sz[PT]),
                        'Cell'.ljust(gc_col_sz[CELL])))
            f.write("+-{}-+-{}-+-{}-+-{}----+-{}----+\n".format(
                        '-' * 4, 
                        '-' * 2,
                        '-' * gc_col_sz[LN],
                        '-' * gc_col_sz[PT],
                        '-' * gc_col_sz[CELL]))
            for i in range(len(gclist)):
                f.write("| {} | {} | {} | {}    | {}    |\n".format(
                            'L'.center(4),
                            gct_list[i][0].rjust(2),
                            str(gclist[i][0][LN]).rjust(gc_col_sz[LN]),
                            gclist[i][0][PT].ljust(gc_col_sz[PT]),
                            gclist[i][0][CELL].ljust(gc_col_sz[CELL])))
                f.write("| {} | {} | {} | {}    | {}    |\n".format(
                            'C'.center(4),
                            gct_list[i][1].rjust(2),
                            str(gclist[i][1][LN]).rjust(gc_col_sz[LN]),
                            gclist[i][1][PT].ljust(gc_col_sz[PT]),
                            gclist[i][1][CELL].ljust(gc_col_sz[CELL])))
                f.write("+-{}-+-{}-+-{}-+-{}----+-{}----+\n".format(
                            '-' * 4, 
                            '-' * 2,
                            '-' * gc_col_sz[LN],
                            '-' * gc_col_sz[PT],
                            '-' * gc_col_sz[CELL]))
            f.write("\n")

            scan_list = [('Launch', sct_list, sc_col_sz)] if len(sct_list) != 0 else []
            if len(ect_list) != 0:
                scan_list.append(('Capture', ect_list, ec_col_sz))

            for ctype, cell_list, col_sz in scan_list:
                f.write("=== Non-CK type cell ({} source):\n".format(ctype))
                f.write("+-{}-+-{}-+-{}----+-{}----+\n".format(
                            '-' * 2,
                            '-' * col_sz[LN],
                            '-' * col_sz[PT],
                            '-' * col_sz[CELL]))
                f.write("| {} | {} | {}    | {}    |\n".format(
                            'CK'.ljust(2), 
                            'Line'.ljust(col_sz[LN]), 
                            'Pin'.ljust(col_sz[PT]),
                            'Cell'.ljust(col_sz[CELL])))
                f.write("+-{}-+-{}-+-{}----+-{}----+\n".format(
                            '-' * 2,
                            '-' * col_sz[LN],
                            '-' * col_sz[PT],
                            '-' * col_sz[CELL]))
                for cell, ctc_status in cell_list:
                    f.write("| {} | {} | {}    | {}    |\n".format(
                                ctc_status.rjust(2),
                                str(cell[LN]).rjust(col_sz[LN]),
                                cell[PT].ljust(col_sz[PT]),
                                cell[CELL].ljust(col_sz[CELL])))
                f.write("+-{}-+-{}-+-{}----+-{}----+\n".format(
                            '-' * 2,
                            '-' * col_sz[LN],
                            '-' * col_sz[PT],
                            '-' * col_sz[CELL]))
                f.write("\n")

    scc_rslt = (scc_rslt[0]+1, *scc_rslt[1:])
    return gcc_rslt, scc_rslt, ctc_rslt
#}}}

def show_path_segment(path: dict, opt_set: set, cons_cfg: dict):
    """Show Path Segment"""  #{{{
    tag, is_1st, is_clk = None, True, True
    slat_list, sdt_list, dlat_list, ddt_list = [], [], [], []
    for cid, cell in enumerate(path['lpath']):
        if tag is None:
            new_tag = None
            for key, ps_re in cons_cfg['pc'].items():
                if (m:=ps_re.fullmatch(cell[PT])):
                    new_tag = key
                    break
            tag = new_tag
            if is_1st:
                is_1st = False
                lat_sum, dt_sum = cell[INCR], cell[DELTA]
            elif new_tag is not None:
                if is_clk:
                    slat_list.append(['TP', lat_sum])
                    sdt_list.append(['TP', dt_sum])
                else:
                    dlat_list.append(['TP', lat_sum])
                    ddt_list.append(['TP', dt_sum])
                lat_sum, dt_sum = cell[INCR], cell[DELTA]
            else:
                lat_sum += cell[INCR]
                dt_sum += cell[DELTA]
        elif cons_cfg['pc'][tag].fullmatch(cell[PT]) is None:
            if is_clk:
                slat_list.append([tag, lat_sum])
                sdt_list.append([tag, dt_sum])
            else:
                dlat_list.append([tag, lat_sum])
                ddt_list.append([tag, dt_sum])
            lat_sum, dt_sum = cell[INCR], cell[DELTA]
            tag = None
            for key, ps_re in cons_cfg['pc'].items():
                if (m:=ps_re.fullmatch(cell[PT])):
                    tag = key
                    break
        else:
            lat_sum += cell[INCR]
            dt_sum += cell[DELTA]

        key = 'TP' if tag == None else tag
        if cid == path['spin']:
            slat_list.append([key, lat_sum])
            sdt_list.append([key, dt_sum])
            tag, is_1st, is_clk = None, True, False 
            lat_sum, dt_sum = 0, 0

    dlat_list.append([key, lat_sum])
    ddt_list.append([key, dt_sum])
    tag, is_1st = None, True
    elat_list, edt_list = [], []

    for cell in path['cpath']:
        if tag is None:
            new_tag = None
            for key, ps_re in cons_cfg['pc'].items():
                if (m:=ps_re.fullmatch(cell[PT])):
                    new_tag = key
                    break
            tag = new_tag
            if is_1st:
                is_1st = False
                lat_sum, dt_sum = cell[INCR], cell[DELTA]
            elif new_tag is not None:
                elat_list.append(['TP', lat_sum])
                edt_list.append(['TP', dt_sum])
                lat_sum, dt_sum = cell[INCR], cell[DELTA]
            else:
                lat_sum += cell[INCR]
                dt_sum += cell[DELTA]
        elif cons_cfg['pc'][tag].fullmatch(cell[PT]) is None:
            elat_list.append([tag, lat_sum])
            edt_list.append([tag, dt_sum])
            lat_sum, dt_sum = cell[INCR], cell[DELTA]
            tag = None
            for key, ps_re in cons_cfg['pc'].items():
                if (m:=ps_re.fullmatch(cell[PT])):
                    tag = key
                    break
        else:
            lat_sum += cell[INCR]
            dt_sum += cell[DELTA]

    key = 'TP' if tag == None else tag
    elat_list.append([key, lat_sum])
    edt_list.append([key, dt_sum])

    print(" Segment:  ", end='')
    if 'pf' in opt_set:
        print("(report path type: full)")
    elif 'pfc' in opt_set:
        print("(report path type: full_clock)")
    elif 'pfce' in opt_set:
        print("(report path type: full_clock_expanded)")
    else:
        print("(report path type: unknown)")
    print(" {}".format("-" * 60))
    print(" data latency: ", end='')
    for tag, val in dlat_list:
        print("{}:{: .4f} ".format(tag, val), end='')
    print()
    print(" data delta:   ", end='')
    for tag, val in ddt_list:
        print("{}:{: .4f} ".format(tag, val), end='')
    print()
    print(" {}".format("-" * 60))
    print(" launch clk latency:  ", end='')
    print("SC:{: .4f} ".format(path['sslat']), end='')
    for tag, val in slat_list:
        print("{}:{: .4f} ".format(tag, val), end='')
    print()
    print(" launch clk delta:    ", end='')
    for tag, val in sdt_list:
        print("{}:{: .4f} ".format(tag, val), end='')
    print()
    print(" {}".format("-" * 60))
    print(" capture clk latency: ", end='')
    print("SC:{: .4f} ".format(path['eslat']), end='')
    for tag, val in elat_list:
        print("{}:{: .4f} ".format(tag, val), end='')
    print()
    print(" capture clk delta:   ", end='')
    for tag, val in edt_list:
        print("{}:{: .4f} ".format(tag, val), end='')
    print()
    print(" {}".format("=" * 60))
#}}}

def show_time_bar(path: dict, opt_set: set, cons_cfg: dict, bar_dtype: set, bar_ptype: set, is_rev: bool):
    """Show Time Path Barchart"""  #{{{
    db, db_dict = [], {}

    ## [c]apacitance
    if 'c' in bar_dtype and 'cap' in opt_set:
        db_dict['c'], data = [], []
        for cid, cell in enumerate(path['lpath']):
            data.append(cell[CAP])
            if cid == path['spin']:
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
            for cell in path['cpath']:
                data.append(cell[CAP])
            db_dict['c'].append(["Capture Clk Cap (pf)", data])

        if ddata is not None:
            db_dict['c'].append(["Path Cap (pf)", ddata])
    else:
        bar_dtype.discard('c')

    opt_set.add('incr')
    dtype_list = [
        ['p', 'phy', PHY, "Distance (um)"],     ## [p]hysical distance
        ['t', 'tran', TRAN, "Tran (ns)"],       ## [t]ransition
        ['d', 'delta', DELTA, "Delta (ns)"],    ## [d]elta
        ['i', 'incr', INCR, "Increment (ns)"],  ## latency [i]ncrement
    ]

    for dtype in dtype_list:
        if dtype[0] in bar_dtype and dtype[1] in opt_set:
            db_dict[dtype[0]], data = [], []
            for cid, cell in enumerate(path['lpath']):
                data.append(cell[dtype[2]])
                if cid == path['spin']:
                    if 'l' in bar_ptype:
                        db_dict[dtype[0]].append([f"Launch Clk {dtype[3]}", data.copy()])
                    if 'd' not in bar_ptype:
                        data = None
                        break
                    if 'f' not in bar_ptype:
                        data = [data[-1]]
            ddata = data

            if 'c' in bar_ptype:
                data = []
                for cell in path['cpath']:
                        data.append(cell[dtype[2]])
                db_dict[dtype[0]].append([f"Capture Clk {dtype[3]}", data])

            if ddata is not None:
                db_dict[dtype[0]].append([f"Path {dtype[3]}", ddata])
        else:
            bar_dtype.discard(dtype[0])

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
        seg_dict = cons_cfg['pc'] if 'pc' in cons_cfg else None
        bar_info, spin_pos = get_time_bar_info(PT, 'TP', seg_dict, bar_ptype, path, True)

        if 'cc' in cons_cfg and 'ct' in bar_dtype:
            bar_ct_info, spin_pos = get_time_bar_info(CELL, 'UN', cons_cfg['cc'], bar_ptype, path, True)
        else:
            bar_dtype.discard('ct')

        bar_ptype.discard('f')
        dtype_cnt, ptype_cnt = len(bar_dtype), len(bar_ptype)
        cy_cnt, cx_cnt = (ptype_cnt, dtype_cnt) if is_rev else (dtype_cnt, ptype_cnt)
        fig, axs = plt.subplots(cy_cnt, cx_cnt, constrained_layout=True)

        pt_anno_list = [[] for i in range(dtype_cnt*ptype_cnt)]
        bbox = dict(boxstyle='round', fc='#ffcc00', alpha=0.6)
        arrow = dict(arrowstyle='->', connectionstyle="arc3,rad=0.")

        if 'ct' in bar_dtype:
            is_ct_chk, last_dtype = True, dtype_cnt-1
        else:
            is_ct_chk = False

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
                handles = [plt.Rectangle((0,0), 1, 1, color=slg[x][label]) for label in labels]
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
                    toks = slv_ce[x][ix][PT].split('/')
                    pin = f".../{toks[-2]}/{toks[-1]}" if len(toks) > 2 else toks
                    if ct_act:
                        val, iy = f"lib: {slv_ce[x][ix][CELL]}", 0.5
                    else:
                        val = "val: {:.4f}".format(iy:=sdb[1][ix])

                    comm = "pin: {}\n{}\nln: {}".format(pin, val, slv_ce[x][ix][LN])
                    pt, = axs.bar(ix, iy, width=1.0, 
                                  color=slv_c[x][ix], hatch=slv_ha[x][ix], ec=slv_ec[x][ix])
                    anno = plt.annotate(comm, xy=(ix,iy), xytext=(dx,dy), 
                                        bbox=bbox, arrowprops=arrow, size=10)
                    anno.set_visible(False)
                    info = {'dx': dx, 'min_dy': min_dy, 'dy_off': dy_off, 'dy_rt': dy_rt, 
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
                            anno.set_y(info['min_dy']+info['dy_off']*info['dy_rt'])
                    plt.draw()
                case 'LR':
                    for i in range(len(pt_anno_list)):
                        for pt, anno, info in pt_anno_list[i]:
                            anno.set_x(anno._x+val)
                    plt.draw()
                case 'PM':
                    for i in range(len(pt_anno_list)):
                        for pt, anno, info in pt_anno_list[i]:
                            info['plv'], toks = (plv:=info['plv']+val), (pin:=info['ce'][PT]).split('/')
                            if len(toks) > plv:
                                pin = ""
                                for i in range(-1, -1-plv, -1):
                                    pin = "/{}".format(toks[i]) + pin
                                pin = '...' + pin
                            toks = anno.get_text().split('\n')
                            anno.set_text(f"pin: {pin}\n{toks[-2]}\n{toks[-1]}")
                    plt.draw()
                case 'BT':
                    for i in range(len(pt_anno_list)):
                        for pt, anno, info in pt_anno_list[i]:
                            toks = anno.get_text().split('\n')
                            if val == 2 and info['ct'] is False:
                                toks[0] = "{}\nlib: {}".format(toks[0], info['ce'][CELL])
                            anno.set_text(f"{toks[0]}\n{toks[-2]}\n{toks[-1]}")
                    plt.draw()
                case 'RESET':
                    for i in range(len(pt_anno_list)):
                        for pt, anno, info in pt_anno_list[i]:
                            if anno._x == -0.5 and info['dy_rt'] == 0.5:
                                info['plv'], toks = 2, (pin:=info['ce'][PT]).split('/')
                                if len(toks) > 2:
                                    pin = f'.../{toks[-2]}/{toks[-1]}'
                                toks = anno.get_text().split('\n')
                                anno.set_text(f"pin: {pin}\n{toks[-2]}\n{toks[-1]}")
                            info['dy_rt'] = 0.5
                            anno.set_x(-0.5)
                            anno.set_y(info['min_dy']+info['dy_off']*info['dy_rt'])
                    plt.draw()

        # fig.canvas.mpl_connect('motion_notify_event', on_move)
        fig.canvas.mpl_connect('button_press_event', on_mouse)
        fig.canvas.mpl_connect('key_press_event', on_key)
        plt.show()
#}}}

def get_time_bar_info(cmp_id: int, default_tag: str, seg_dict: None, bar_ptype: set, path: dict, 
                      is_order=False):
    """Get Time Bar Information"""  #{{{
    pal_num = len(HIST_PALETTE)
    if seg_dict is not None and is_order:
        hist_palette = {}
        for i, key in enumerate(seg_dict.keys()):
            hist_palette[key] = HIST_PALETTE[i%pal_num]
    else:
        hist_palette = HIST_PALETTE

    default_color = HIST_PALETTE[0] if seg_dict is None else HIST_DEFAULT_COLOR
    bar_lg, spin_pos = [], (None, None)
    lv_ce, lv_c, lv_ha, lv_ec = [], [], [], []

    for type_ in ('l', 'c', 'd'):
        if type_ in bar_ptype:
            tag, pal_idx, bar_lg_path = None, -1, {default_tag: default_color}
            lv_ce_path, lv_c_path, lv_ha_path, lv_ec_path  = [], [], [], []
            s_path = path['cpath'] if type_ == 'c' else path['lpath']
            for cid, cell in enumerate(s_path):
                if seg_dict is None:
                    pass
                elif tag is None:
                    new_tag = None
                    for key, ps_re in seg_dict.items():
                        if (m:=ps_re.fullmatch(cell[cmp_id])):
                            new_tag = key
                            break
                    tag = new_tag
                elif seg_dict[tag].fullmatch(cell[cmp_id]) is None:
                    new_tag = None
                    for key, ps_re in seg_dict.items():
                        if (m:=ps_re.fullmatch(cell[cmp_id])):
                            new_tag = key
                            break
                    tag = new_tag

                if cid == path['spin'] and type_ == 'd' and 'f' not in bar_ptype:
                    pal_idx, bar_lg_path = -1, {default_tag: default_color}
                    lv_ce_path, lv_c_path, lv_ha_path, lv_ec_path  = [], [], [], []

                key = default_tag if tag is None else tag
                if key not in bar_lg_path:
                    if is_order:
                        bar_lg_path[key] = hist_palette[key]
                    else:
                        bar_lg_path[key] = hist_palette[(pal_idx:=pal_idx+1)%pal_num]

                lv_ce_path.append(cell)

                lv_c_path.append(bar_lg_path[key])
                if cid == path['spin'] and type_ == 'd':
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
#}}}

def key_event_check(action):
    """Check Key Event"""  #{{{
    if action == 'escape'   : return 'ESC'  ,  0    # remove all comment bubble
    if action == 'up'       : return 'UD'   ,  0.1  # up shift bubble
    if action == 'down'     : return 'UD'   , -0.1  # down shift bubble
    if action == 'left'     : return 'LR'   , -0.5  # left shift bubble
    if action == 'right'    : return 'LR'   ,  0.5  # right shift bubble
    if action == 'a'        : return 'PM'   ,  1    # increase pin hierarchical
    if action == 'd'        : return 'PM'   , -1    # decrease pin hierarchical
    if action == '1'        : return 'BT'   ,  1    # bubble type 1 (pin, val, ln)
    if action == '2'        : return 'BT'   ,  2    # bubble type 2 (pin, lib, val, ln)
    if action == 'r'        : return 'RESET',  0    # reset bubble
    return "NONE", 0
#}}}

### Main ###

def create_argparse() -> argparse.ArgumentParser:
    """Create Argument Parser"""  #{{{
    parser = argparse.ArgumentParser(
                formatter_class=argparse.RawTextHelpFormatter,
                description="PrimeTime Report Analysis\n" + 
                            "-- Timing Path Summary\n" +
                            "-- command: report_timing")

    parser.add_argument('-version', action='version', version=VERSION)
    parser.add_argument('rpt_fp', help="report_path") 
    parser.add_argument('-c', dest='cfg_fp', metavar='<config>', 
                                  help="set the config file path") 
    parser.add_argument('-nc', dest='is_nocfg', action='store_true', 
                                  help="disable to load the config file")
    parser.add_argument('-r', dest='range', metavar='<value>', 
                                  help="report scan range select, ex: 6,16+2,26-100 \n" +
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
#}}}

def main():
    """Main Function"""  #{{{
    parser = create_argparse()
    args = parser.parse_args()
    default_cfg = ".pt_ana_ts.setup"

    if args.is_nocfg:
        args.cfg_fp = None
    elif args.cfg_fp is None and os.path.exists(default_cfg):
        if os.path.isfile(default_cfg):
            args.cfg_fp = default_cfg

    prange_list = []
    if args.range is None:
        prange_list.append([0, None, 1])
    else:
        for prange in args.range.split(','):
            if (m:=prange_re1.fullmatch(args.range)):
                prange_list.append([int(m[1]), None, int(m[2])])
            elif (m:=prange_re2.fullmatch(args.range)): 
                prange_list.append([int(m[1]), int(m[2]), None])
            else:
                prange_list.append([int(args.range), None, 1])
    
    print("\n Report: {}\n".format(os.path.abspath(args.rpt_fp)))
    report_time_summary(args, prange_list)
#}}}

if __name__ == '__main__':
    main()
