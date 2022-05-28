#!/usr/bin/env python3
# -*- coding: utf-8 -*-
## +FHDR=======================================================================
## Copyright (c) 2022 Hsin-Hsien Yeh (Edward Yeh).
## All rights reserved.
## ----------------------------------------------------------------------------
## Filename         : pt_vio_ana.py
## File Description : 
## ----------------------------------------------------------------------------
## Author           : Edward Yeh
## Created On       : Sat, Jan 29, 2022  5:46:03 PM
## Format           : Python module
## ----------------------------------------------------------------------------
## Reuse Issues     : 
## ----------------------------------------------------------------------------
## Release History  : 
## -FHDR=======================================================================

import os, gzip, re, sys
import argparse, textwrap, pickle

### Global Parameter ###  

#{{{
is_debug = False

PARTITION_PREFIX = 'chip_top'

TIME_VIO_TYPES = (
    'max_delay/setup',
    'min_delay/hold',
    'removal',
    'clock_gating_hold'
)

DRC_VIO_TYPES = (
    'max_capacitance',
    'min_capacitance',
    'max_transition',
    'min_transition'
)

VIO_TYPES = TIME_VIO_TYPES + DRC_VIO_TYPES

keywords = ['*']
databases = {}
slack_thds = {}
#}}}

### Sub Function ###

def load_cfg(cfg_fp: str):
    """Load configuration"""  #{{{
    with open(cfg_fp, 'r') as f:
        key_act = False
        tmp_key = []

        for line in f:
            toks = line.split()

            if len(toks) == 0:
                continue

            try:
                if key_act:
                    if toks[0][-1] == ':':
                        keywords.extend(tmp_key)
                        key_act = False
                    else:
                        for key in toks:
                            if key.startswith('#'):
                                break
                            else:
                                tmp_key.append(key)

                if toks[0].startswith('#'):
                    pass
                elif toks[0] == 'partition_prefix:':
                    PARTITION_PREFIX = toks[1]
                elif toks[0] == 'db:':
                    dtype, vtype, vpath = toks[1:4]
                    load_db(dtype, vtype, vpath)
                elif toks[0] == 'keyword:':
                    if keywords[0] == '*':
                        del keywords[:]
                    key_act = True
                    tmp_key = []

            except Exception:
                print(f"[WARNING] syntax error, ignore. (line: {line[:-1]})")

        if key_act:
            keywords.extend(tmp_key)

        if is_debug:
            print("=== Configuration Infomation ===")
            print(f"PARTITION_PREFIX: {PARTITION_PREFIX}")
            print("KEYWORD:")
            for key in keywords:
                print(f"  {key}")
            input("\n(Press enter to continue.)\n")
#}}}

def load_db(dtype: str, vtype: str, vpath: str):
    """Load violation databases"""  #{{{
    print(f"[load_db] database_type, violation_type = {dtype}, {vtype}", end='')

    try:
        if vtype in TIME_VIO_TYPES:
            with open(vpath, 'rb') as f:
                new_db = pickle.load(f)
        elif vtype in DRC_VIO_TYPES:
            new_db = load_drc_db(vpath)
        else:
            print(" ... ignore.")
            return

        db = databases.setdefault(vtype, {})
        db[dtype] = new_db 
        print(" ... pass.")

    except Exception:
        print(" ... fail.")
#}}}

def load_drc_db(vpath: str) -> dict:
    """Load DRC violation database"""  #{{{
    drc_db = {}
    with open(vpath) as f:
        for line in f:
            try:
                direct, src, dst = line.split()
                src_dict = drc_db.setdefault(src, {'in': [], 'out': []})
                if direct[:-1] in src_dict:
                    src_dict[direct[:-1]].append(dst)
            except ValueError:
                pass
    return drc_db
#}}}

def load_sl_thd(cfg_fp: str):
    """Load slack threshold"""  #{{{
    print(f"[load_sl_thd] load slack threshold", end='')

    try:
        with open(cfg_fp) as f:
            line_no = 0
            for line in f:
                try:
                    tag, vtype, ctype, value = line.split()
                    if tag == 'sl:':
                       slack_thds[vtype] = (ctype, float(value)) 
                except Exception:
                    pass 
            print(" ... pass.")
    except Exception:
        print(" ... fail.")

    if is_debug:
        print("=== Slack Threshold Infomation ===")
        for vtype in zip(slack_thds.keys()):
            print(f"  {vtype} {slack_thds[vtype][0]} {slack_thds[vtype][1]}")
        input("\n(Press enter to continue.)\n")
#}}}

def get_path_info(toks, f, is_multi: bool) -> tuple:
    """Extract path information"""  #{{{
    end_point = toks[0]  # end point
    del toks[0]

    if is_multi:
        if len(toks) == 0:  # corner
            line = f.readline()
            toks = line.split()
        corner = toks[0]
        del toks[0]
    else:
        corner = 'single' 

    if len(toks) == 0:  # require delay
        line = f.readline()
        toks = line.split()
    # r_delay = float(toks[0])
    del toks[0]

    if len(toks) == 0:  # arrival delay
        line = f.readline()
        toks = line.split()
    # a_delay = float(toks[0])
    del toks[0]

    if len(toks) == 0:  # slack
        line = f.readline()
        toks = line.split()
    slack = float(toks[0])
    del toks[0]

    return end_point, corner, slack 
#}}}

def get_ref_vio_path(ref_fp: str, is_multi: bool) -> dict:
    """Parse violation path from reference report"""  #{{{
    ref_vio_path = {}
    for vio_type in VIO_TYPES:
        ref_vio_path[vio_type] = {}

    if os.path.splitext(ref_fp)[1] == '.gz':
        f = gzip.open(ref_fp, mode='rt')
    else:
        f = open(ref_fp)

    line = f.readline()
    while line:
        line = line.strip()
        is_group = False

        if len(line) == 0:
            vio_type = None
            line = f.readline()
            continue

        toks = line.split()

        if toks[0] in ref_vio_path:
            is_group = True
            vio_type = toks[0]
            for i in range(4):
                line = f.readline()

        if vio_type is not None and not is_group:
            end_point, corner, _ = get_path_info(toks, f, is_multi)
            if end_point not in ref_vio_path[vio_type]:
                ref_vio_path[vio_type][end_point] = set()
            ref_vio_path[vio_type][end_point].add(corner)

        line = f.readline()
    f.close()
    return ref_vio_path
#}}}

def pair_match(db: dict, vio_type: str, vio_path: tuple, ref_corners: tuple) -> str:
    """Check if path is existed in both databases"""  #{{{
    if vio_type not in db:
        return 'bypass'
    else:
        end_point, corner, slack = vio_path
        try:
            tar_start = db[vio_type]['tar'][corner][end_point][slack]
        except KeyError:
            if is_debug:
                print("===")
                print("[pair_target_unexisted]")
                print(f"  Endpoint: {end_point}")
                print(f"  Corner:   {corner}")
                print(f"  Slack:    {slack}")
                print("===")
            return 'bypass'

        ref_starts = set()
        for ref_c in ref_corners:
            try:
                ref_c_starts = db[vio_type]['ref'][ref_c][end_point]
            except KeyError:
                pass
            else:
                ref_starts.update(ref_c_starts.values())

        if tar_start in ref_starts:
            return 'yes'
        else:
            if is_debug:
                print("===")
                print("[pair_check_no]")
                print(f"  Endpoint:   {end_point}")
                print(f"  Startpoint: {tar_start}")
                print(f"  Corner:     {corner}")
                print(f"  Slack:      {slack}")
                print(f"  RefCorners: {ref_corners}")
                print(f"  RefStarts:  {ref_starts}")
                print("===")
            return 'no'
#}}}

### Main Function ###

def main():
    """ Main Function """  #{{{
    parser = argparse.ArgumentParser(
                formatter_class=argparse.RawTextHelpFormatter,
                description="PrimeTime violation report analysis.")

    parser.add_argument('rpt_in_fn', type=str, help="primetime report file name")
    parser.add_argument('rpt_out_fn', type=str, help="output report file name")

    parser.add_argument('--cfg', dest='cfg_fp', metavar='<path>', type=str,
                                    help="tool configuration file")

    parser.add_argument('--multi', dest='is_multi', action='store_true',
                                    help="enable multi-corner check")
    parser.add_argument('--part', dest='part_name', metavar='<name>', type=str,
                                    help="only report assigned partition")
    parser.add_argument('--sl_thd', dest='sl_thd_fp', metavar='<path>', type=str,
                                    help="filter by slack threshold")

    parser.add_argument('--kw_ed', dest='kw_ed_mode', metavar='<mode>', type=str,
                                    help="endpoint key filter (mode: in/ex)")
    parser.add_argument('--kw_st', dest='kw_st_mode', metavar='<mode>', type=str,
                                    help="startpoint key filter (mode: in/ex, need target DB)")

    parser.add_argument('--diff', dest='diff_rpt_fp', metavar='<ref_rpt>', type=str,
                                    help="report difference set based reference report")
    parser.add_argument('--inter', dest='inter_rpt_fp', metavar='<ref_rpt>', type=str,
                                    help="report intersection set based reference report")
    parser.add_argument('--pair', dest='is_pair_chk', action='store_true',
                                    help="enable start/end point check (setup/hold only, need reference DB)")

    parser.add_argument('--show_st', dest='is_show_st', action='store_true',
                                    help="show startpoint in report (need target DB)")
    parser.add_argument('--wpath', dest='is_wpath', action='store_true',
                                    help="only worst path in report")
    parser.add_argument('--wslack', dest='is_wslack', action='store_true',
                                    help="only worst slack in report")
    parser.add_argument('--only_sum', dest='is_onlysum', action='store_true',
                                    help="only summary in report")

    parser.add_argument('--drc_dump', dest='drc_dump_mode', metavar='<mode>', type=str,
                                    help="dump DRC violation point (mode: all/in/ex)")

    args = parser.parse_args()

    ## Process Start ##

    vio_cnt = {}
    vio_worst = {}
    vio_cnt_part = {}
    vio_worst_part = {}

    for vio_type in VIO_TYPES:
        vio_cnt[vio_type] = 0
        vio_worst[vio_type] = 0.0
        vio_cnt_part[vio_type] = {}
        vio_worst_part[vio_type] = {}

    if args.cfg_fp:
        load_cfg(args.cfg_fp)

    if args.sl_thd_fp:
        load_sl_thd(args.sl_thd_fp)

    if args.diff_rpt_fp is not None:
        op_mode = 'diff'
        ref_fp = args.diff_rpt_fp
    elif args.inter_rpt_fp is not None:
        op_mode = 'inter'
        ref_fp = args.inter_rpt_fp
    else:
        op_mode = 'default'

    if op_mode != 'default':
        ref_vio_path = get_ref_vio_path(ref_fp, args.is_multi)

    if args.drc_dump_mode:
        drc_vio_point = {}
        for drc_type in DRC_VIO_TYPES:
            drc_vio_point[drc_type] = []

    if os.path.splitext(args.rpt_in_fn)[1] == '.gz':
        try:
            in_file = gzip.open(args.rpt_in_fn, mode='rt')
        except Exception:
            rpt_fn = args.rpt_in_fn[:-3]
            if os.path.exists(rpt_fn):
                print("[WARNING] gzip report unexisted but non-gzip report detected, change path and load.")
                in_file = open(rpt_fn)
            else:
                print("[ERROR] gzip report unexisted (even non-gzip type)")
                exit(1)
    else:
        try:
            in_file = open(args.rpt_in_fn)
        except Exception:
            rpt_fn = args.rpt_in_fn + ".gz"
            if os.path.exists(rpt_fn):
                print("[WARNING] non-gzip report unexisted but gzip report detected, change path and load.")
                in_file = gzip.open(rpt_fn, mode='rt')
            else:
                print("[ERROR] non-gzip report unexisted (even gzip type)")
                exit(1)

    out_file = open(args.rpt_out_fn, 'w')
    sys.stdout = out_file

    if args.is_wpath:
        print("========================================")
        print("  Worst Violation Path")
        print("========================================")
    elif args.is_wslack:
        print("========================================")
        print("  Worst Violation Slack")
        print("========================================")
    elif not args.is_onlysum:
        print("========================================")
        print("  Violation Path")
        print("========================================")

    is_first = False
    is_skip = False
    group_name = None
    vio_type = None

    line = in_file.readline()
    while line:
        line = line.strip()
        is_group = False

        if len(line) == 0:
            vio_type = None
            line = in_file.readline()
            continue

        toks = line.split()

        if toks[0] in vio_cnt:
            is_group = True
            is_first = True
            is_skip = False
            group_name = line
            vio_type = toks[0]
            for i in range(4):
                line = in_file.readline()

        if vio_type is not None and not is_group:
            vio_path = get_path_info(toks, in_file, args.is_multi)
            end_point, corner, slack = vio_path

            if args.drc_dump_mode and vio_type in DRC_VIO_TYPES:
                drc_vio_point[vio_type].append(end_point)

            for keyword in keywords:
                if keyword == '*' or args.kw_ed_mode is None:
                    key_match = 'p'  # bypass

                elif args.kw_ed_mode == 'in':
                    key_match = 'y' if re.search(keyword, end_point) else 'n'
                    if key_match == 'n' and vio_type in DRC_VIO_TYPES:
                        if vio_type in databases:
                            try:
                                for endp in databases[vio_type]['tar'][end_point]['out']:
                                    if re.search(keyword, endp):
                                        key_match = 'yd'
                                        break
                            except KeyError:
                                pass

                elif args.kw_ed_mode == 'ex':
                    key_match = 'n' if re.search(keyword, end_point) else 'y'
                    if key_match == 'y' and vio_type in DRC_VIO_TYPES:
                        key_match = 'yd'
                        if vio_type in database:
                            try:
                                for endp in databases[vio_type]['tar'][end_point]['out']:
                                    if re.search(keyword, endp):
                                        key_match = 'n'
                                        break
                            except KeyError:
                                pass
                else:
                    key_match = 'p'  # bypass

                if key_match != 'n' and op_mode == 'diff':
                    is_ignore = end_point in ref_vio_path[vio_type]
                    if vio_type in TIME_VIO_TYPES and is_ignore and args.is_pair_chk:
                        ref_corners = tuple(ref_vio_path[vio_type][end_point])
                        pair_check = pair_match(databases, vio_type, vio_path, ref_corners)
                        is_ignore = False if pair_check == 'no' else True
                elif key_match != 'n' and op_mode == 'inter':
                    is_ignore = end_point not in ref_vio_path[vio_type]
                    if vio_type in TIME_VIO_TYPES and not is_ignore and args.is_pair_chk:
                        ref_corners = tuple(ref_vio_path[vio_type][end_point])
                        pair_check = pair_match(databases, vio_type, vio_path, ref_corners)
                        is_ignore = True if pair_check == 'no' else False
                else:
                    is_ignore = False

                if key_match != 'n' and not is_ignore:
                    try:
                        if vio_type in DRC_VIO_TYPES:
                            start_point = None
                        else:
                            start_point = databases[vio_type]['tar'][corner][end_point][slack]
                    except KeyError:
                        start_point = None

                    if args.kw_st_mode is not None:
                        if vio_type in DRC_VIO_TYPES:
                            if key_match == 'y':
                                pass
                            else:
                                start_hit = 'n'
                                start_list = databases[vio_type]['tar'][end_point]['in']

                                for keyword2 in keywords:
                                    if keyword2 == '*' or len(start_list) == 0:
                                        start_hit = 'p'
                                        break
                                    else:
                                        for startp in start_list:
                                            if re.search(keyword2, startp):
                                                start_hit = 'y'
                                                break
                                        if start_hit == 'y':
                                            break

                                if args.kw_st_mode == 'in' and start_hit == 'n':
                                    break
                                if args.kw_st_mode == 'ex' and start_hit == 'y':
                                    break

                        elif vio_type in TIME_VIO_TYPES:
                            if start_point is not None:
                                start_hit = 'n'
                                for keyword2 in keywords:
                                    if keyword2 == '*':
                                        start_hit = 'p'
                                        break
                                    else:
                                        if re.search(keyword2, start_point):
                                            start_hit = 'y'
                                            break

                                if args.kw_st_mode == 'in' and start_hit == 'n':
                                    break
                                if args.kw_st_mode == 'ex' and start_hit == 'y':
                                    break

                    chip_part = end_point.split('/')[0]
                    if args.part_name is not None and args.part_name != chip_part:
                        break
                    elif not chip_part.startswith(PARTITION_PREFIX):
                        chip_part = 'other'

                    if vio_type in slack_thds:
                        ctype, value = slack_thds[vio_type]
                        if ctype == '<':
                            if slack >= value:
                                break
                        elif ctype == '<=':
                            if slack > value:
                                break
                        elif ctype == '==':
                            if slack != value:
                                break
                        elif ctype == '>=':
                            if slack < value:
                                break
                        elif ctype == '>':
                            if slack <= value:
                                break

                    vio_cnt[vio_type] += 1
                    vio_cnt_part[vio_type][chip_part] = vio_cnt_part[vio_type].get(chip_part, 0) + 1

                    if slack < vio_worst[vio_type]:
                        vio_worst[vio_type] = slack

                    if slack < vio_worst_part[vio_type].setdefault(chip_part, 0.0):
                        vio_worst_part[vio_type][chip_part] = slack

                    if not args.is_show_st:
                        start_point = None

                    if args.is_wpath:
                        if not is_skip:
                            print(f"\n{group_name}")
                            print('-' * 75)
                            if start_point is not None:
                                print(f"S: {start_point}\nE: ", end='')
                            print(f"{end_point}\n{slack:16.4f}", end='')
                            if args.is_multi:
                                print("    ({corner})")
                            else:
                                print()

                    elif args.is_wslack:
                        if not is_skip:
                            print(f"{group_name:50}:{slack:11.4f}", end='')
                            if args.is_multi:
                                print(f"  ({corner})")
                            else:
                                print()

                    elif not args.is_onlysum:
                        if is_first:
                            print(f"\n{group_name}")
                            print('-' * 75)
                            is_first = False
                        if start_point is not None:
                            print(f"S: {start_point}\nE: ", end='')
                        print(f"{end_point}\n{slack:16.4f}", end='')
                        if args.is_multi:
                            print(f"    ({corner})")
                        else:
                            print()

                    is_skip = True
                    break
        line = in_file.readline()
    in_file.close()

    print()

    ## Print Summary ##

    if not args.is_wpath and not args.is_wslack:
        print("========================================")
        print("  Violation Summary")
        print("========================================")

        if args.part_name is None:
            tag = 'chip'
        else:
            tag = args.part_name

        print(f"\nWorst Negtive Slack ({tag})")
        print("========================================")
        for key, val in vio_worst.items():
            if key in slack_thds:
                ctype, thd = slack_thds[key]
                print(f"{key:20}: {val: 4.4f} (slack {ctype} {thd:.4f})")
            else:
                print(f"{key:20}: {val: 4.4f}")
        print()

        print(f"\nNumber of Violations ({tag})")
        print("========================================")
        for key, val in vio_cnt.items():
            if key in slack_thds:
                ctype, thd = slack_thds[key]
                print(f"{key:20}: {val:<7} (slack {ctype} {thd:.4f})")
            else:
                print(f"{key:20}: {val:<7}")
        print()

        if args.part_name is None:
            print("\nWorst Negtive Slack (partition)")
            print("========================================")
            for key, parts in vio_worst_part.items():
                if key in slack_thds:
                    ctype, thd = slack_thds[key]
                    print("{:<20} (slack {} {:.4f})".format(key+':', ctype, thd))
                else:
                    print("{}:".format(key))

                if len(parts) == 0:
                    print("  No violation.")
                else:
                    for part, val in sorted(parts.items(), key=lambda x:x[0]):
                        print(f"  {part:20}: {val: 4.4f}")
            print()

            print("\nNumber of Violations (partition)")
            print("========================================")
            for key, parts in vio_cnt_part.items():
                if key in slack_thds:
                    ctype, thd = slack_thds[key]
                    print("{:<20} (slack {} {:.4f})".format(key+':', ctype, thd))
                else:
                    print("{}:".format(key))

                if len(parts) == 0:
                    print("  No violation.")
                else:
                    for part, val in sorted(parts.items(), key=lambda x:x[0]):
                        print(f"  {part:20}: {val:<7}")
            print()

    out_file.close()

    ### Dump DRC violation point ###

    if args.drc_dump_mode:
        for drc_type in DRC_VIO_TYPES:
            if args.drc_dump_mode == 'all':
                with open(drc_type + ".list", "w") as f:
                    for point in drc_vio_point[drc_type]:
                        f.write(point + "\n")

            elif args.drc_dump_mode == 'in':
                with open(drc_type + ".in.list", "w") as f:
                    for point in drc_vio_point[drc_type]:
                        key_act = False
                        for keyword in keywords:
                            if re.search(keyword, point):
                                key_act = True
                                break
                        if key_act is True:
                            f.write(point + "\n")

            elif args.drc_dump_mode == 'ex':
                with open(drc_type + ".ex.list", "w") as f:
                    for point in drc_vio_point[drc_type]:
                        key_act = False
                        for keyword in keywords:
                            if re.search(keyword, point):
                                key_act = True
                                break
                        if key_act is False:
                            f.write(point + "\n")
#}}}

if __name__ == '__main__':
    main()
else:
    pass
