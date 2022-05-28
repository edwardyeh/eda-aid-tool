#!/usr/bin/env python3
# -*- coding: utf-8 -*-
## +FHDR=======================================================================
## Copyright (c) 2022 Hsin-Hsien Yeh (Edward Yeh).
## All rights reserved.
## ----------------------------------------------------------------------------
## Filename         : pt_vio_extract.py
## File Description : 
## ----------------------------------------------------------------------------
## Author           : Edward Yeh
## Created On       : Fri 28 Jan 2022 09:26:28 PM CST
## Format           : Python module
## ----------------------------------------------------------------------------
## Reuse Issues     : 
## ----------------------------------------------------------------------------
## Release History  : 
## -FHDR=======================================================================

import os, gzip, pickle, re
import argparse, textwrap

# ref_db: {corner: path_dict, ...}
#                  +--{endpoint: fanin_dict, ...}
#                                +--{slack: startpoint, ...}

### Sub Function ###

def update_db(ref_db: dict, corner: str, rpt_fp: str):
    """Extract paths from report and update database"""  #{{{
    if os.path.splitext(rpt_fp)[1] == '.gz':
        f = gzip.open(rpt_fp, mode='rt')
    else:
        f = open(rpt_fp)

    path_dict = {}
    pathe = paths = ''
    endp = startp = 'NoSingal'
    is_feedback = False
    is_path_done = False

    line = f.readline()
    while line:
        line = line.strip()
        if line == '':
            line = f.readline()
            continue

        toks = line.split()
        pair_end = ' '.join(toks[0:3]) if len(toks) >= 3 else ''

        if pair_end == 'data arrival time' and not is_path_done:
            is_path_done = True
            path = (pathe, paths)
        elif toks[0] == 'slack':
            endp = startp = 'NoSingal'
            is_feedback = False
            is_path_done = False
            if toks[1] == '(VIOLATED)':
                value = float(toks[2])
                if path[0] in path_dict:
                    path_dict[path[0]][value] = path[1]
                else:
                    path_dict[path[0]] = {value: path[1]}
        elif toks[0] == 'Startpoint:':
            startp = toks[1]
        elif toks[0] == 'Endpoint:':
            endp = toks[1]
            if endp == startp:
                is_feedback = True
        elif toks[0].startswith(endp):
            if is_feedback:
                paths = pathe
            pathe = toks[0]
        elif toks[0].startswith(startp):
            paths = toks[0]

        line = f.readline()

    f.close()
    ref_db[corner] = path_dict
#}}}

### Main Function ###

def main(is_debug: bool):
    """Main Function"""  #{{{
    parser = argparse.ArgumentParser(
                formatter_class=argparse.RawTextHelpFormatter,
                description=textwrap.dedent("""
                    PrimeTime violation path extractor.

                    Extract start-end violation path from reports.
                """))

    parser.add_argument('rpt_dir', metavar='report_dir', type=str, 
                                    help="report directory")
    parser.add_argument('base_fn', metavar='base_fn', type=str, 
                                    help="basename of report file")
    parser.add_argument('--multi', dest='corner_fp', metavar='<path>', type=str, 
                                    help="set corner list and enable multi-corner mode")
    parser.add_argument('-o', dest='outdb_fp', metavar='<path>', type=str, 
                                    help="database output path (default: ./pt_vio.db)")
    parser.add_argument('-O', dest='outdb_fp_f', metavar='<path>', type=str, 
                                    help="database output path, force overwrite")

    args = parser.parse_args()

    if args.outdb_fp is not None:
        if os.path.exists(args.outdb_fp):
            ret = input("File existed, overwrite? (y/n) ")
            if ret.lower() == 'n':
                exit(0)
        outdb_fp = args.outdb_fp
    elif args.outdb_fp_f is not None:
        outdb_fp = args.outdb_fp_f
    else:
        outdb_fp = "pt_vio.db"

    ref_db = {}
    base_fn = os.path.basename(args.base_fn)

    if args.corner_fp == None:
        rpt_fp = os.path.join(args.rpt_dir, base_fn)
        update_db(ref_db, 'single', rpt_fp)
    else:
        with open(args.corner_fp) as f:
            for corner in f.readlines():
                corner = corner[:-1]
                rpt_fp = os.path.join(args.rpt_dir, corner, base_fn)

                try:
                    if not os.path.exists(rpt_fp):
                        if os.path.splitext(rpt_fp)[1] == '.gz':
                            print("[Warning] gzip report unexisted, try to find non-gzip report. ")
                            rpt_fp = rpt_fp[:-3]
                        else:
                            print("[Warning] non-gzip report unexisted, try to find gzip report. ")
                            rpt_fp += ".gz"

                        if not os.path.exists(rpt_fp):
                            raise Exception

                    update_db(ref_db, corner, rpt_fp)
                except Exception:
                    print(f"[Corner Unexist] {corner}")

    total_path_cnt = 0
    for corner, path_dict in ref_db.items():
        corner_path_cnt = 0
        for pathe, fanin_dict in path_dict.items():
            for value, paths in fanin_dict.items():
                corner_path_cnt += 1
                if is_debug:
                    print('C:{}\nS:{}\nE:{}\n{}\n---\n'.format(corner, paths, pathe, value))
        print('{}: {}'.format(corner, corner_path_cnt))
        total_path_cnt += corner_path_cnt
    print('total path count: {}'.format(total_path_cnt))

    with open(outdb_fp, 'wb') as f:
        pickle.dump(ref_db, f)
#}}}

if __name__ == '__main__':
    main(False)
else:
    pass
