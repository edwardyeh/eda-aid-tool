#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-only
#
# Layout Check Tool
#
# Copyright (C) 2025 Yeh, Hsin-Hsien <yhh76227@gmail.com>
#
import argparse
import datetime
import json
import shutil
import sys
from jsonschema import validate, ValidationError
from pathlib import Path
from .utils.def_parser import DEFParser
from .utils.lef_parser import LEFParser


##############################################################################
### Global Variable

CLK_2W2S_SCHEMA = {
    '$schema': 'https://json-schema.org/draft/2020-12/schema',
    'type': 'object',
    'additionalProperties': False,
    'required': ['unit', 'pass_ratio', 'type', 'block'],
    'properties': {
        'unit': {'type': 'number'},
        'pass_ratio': {'type': 'number'},
        'type': {'enum': ['top', 'block']},
        'block': {
            'type': 'object',
            'additionalProperties': False,
            'patternProperties': {
                r'\S+': {
                    'type': 'object',
                    'additionalProperties': False,
                    'required': ['def', 'clk'],
                    'properties': {
                        'def': {'type': 'string'},
                        'clk': {
                            'type': 'object',
                            'additionalProperties': False,
                            'patternProperties': {
                                r'\S+': {
                                    'type': 'array',
                                    'items': {
                                        'type': 'object',
                                        'additionalProperties': False,
                                        'required': ['stp', 'edp', 'net'],
                                        'properties': {
                                            'stp': {'type': 'string'},
                                            'edp': {'type': 'string'},
                                            'net': {
                                                'type': 'array',
                                                'minItems': 1,
                                                'items': {'type': 'string'}
                                            }
                                        }
                                    }
                                }
                            }
                        },
                        'path_ratio': {
                            'type': 'object',
                            'additionalProperties': False,
                            'patternProperties': {
                                r'\S+:\S+': {'type': 'number'}
                            }
                        },
                        'net_waive': {
                            'type': 'array',
                            'items': {'type': 'string'}
                        }
                    }
                }
            }
        }
    }
}

BOUND_WIRE_OUT_SCHEMA = {
    '$schema': 'https://json-schema.org/draft/2020-12/schema',
    'type': 'object',
    'additionalProperties': False,
    'required': ['unit', 'margin', 'type', 'block'],
    'properties': {
        'unit': {'type': 'number'},
        'margin': {'type': 'number'},
        'type': {'enum': ['top', 'block']},
        'block': {
            'type': 'object',
            'additionalProperties': False,
            'patternProperties': {
                r'\S+': {
                    'type': 'object',
                    'additionalProperties': False,
                    'required': ['def', 'net'],
                    'properties': {
                        'def': {'type': 'string'},
                        'net': {
                            'type': 'array',
                            'minItems': 1,
                            'items': {'type': 'string'}
                        }
                    }
                }
            }
        }
    }
}

MACRO_WIRE_OUT_SCHEMA = {
    '$schema': 'https://json-schema.org/draft/2020-12/schema',
    'type': 'object',
    'additionalProperties': False,
    'required': ['unit', 'lefs', 'type', 'block'],
    'properties': {
        'unit': {'type': 'number'},
        'lefs': {
            'type': 'array',
            'minItems': 1,
            'items': {'type': 'string'}
        },
        'type': {'enum': ['top', 'block']},
        'block': {
            'type': 'object',
            'additionalProperties': False,
            'patternProperties': {
                r'\S+': {
                    'type': 'object',
                    'additionalProperties': False,
                    'required': ['def', 'macro'],
                    'properties': {
                        'def': {'type': 'string'},
                        'macro': {
                            'type': 'array',
                            'minItems': 1,
                            'items': {
                                'type': 'object',
                                'additionalProperties': False,
                                'required': ['inst', 'ref', 'margin', 'net'],
                                'properties': {
                                    'inst': {'type': 'string'},
                                    'ref': {'type': 'string'},
                                    'margin': {'type': 'number'},
                                    'net': {
                                        'type': 'array',
                                        'minItems': 1,
                                        'items': {'type': 'string'}
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

MACRO_CELL_OUT_SCHEMA = {
    '$schema': 'https://json-schema.org/draft/2020-12/schema',
    'type': 'object',
    'additionalProperties': False,
    'required': ['unit', 'lefs', 'type', 'block'],
    'properties': {
        'unit': {'type': 'number'},
        'lefs': {
            'type': 'array',
            'minItems': 1,
            'items': {'type': 'string'}
        },
        'type': {'enum': ['top', 'block']},
        'block': {
            'type': 'object',
            'additionalProperties': False,
            'patternProperties': {
                r'\S+': {
                    'type': 'object',
                    'additionalProperties': False,
                    'required': ['def', 'macro'],
                    'properties': {
                        'def': {'type': 'string'},
                        'macro': {
                            'type': 'array',
                            'minItems': 1,
                            'items': {
                                'type': 'object',
                                'additionalProperties': False,
                                'required': ['inst', 'ref', 'margin', 'cell'],
                                'properties': {
                                    'inst': {'type': 'string'},
                                    'ref': {'type': 'string'},
                                    'margin': {'type': 'number'},
                                    'cell': {
                                        'type': 'array',
                                        'minItems': 1,
                                        'items': {'type': 'string'}
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}


##############################################################################
### Procedure


def check_2w2s_flow(out_fpath, config: dict, def_parser_dict: dict) -> bool:
    """Clock 2W2S check flow."""
    unit2x_pre = 2 * config['unit']
    is_top = (config['type'] == 'top')
    out_fp = sys.stdout if out_fpath is None else open(out_fpath, 'w')

    for blk, blk_data in config['block'].items():
        def_info = def_parser_dict[blk].def_dict
        unit2x = unit2x_pre * (dbu := def_info['unit']['percision'])
        prefix = f'{blk}/' if is_top else ''

        # Get check waive
        if 'path_ratio' in blk_data:
            is_adj, adj_dict = True, blk_data['path_ratio']
        else:
            is_adj, adj_dict = False, {}

        if 'net_waive' in blk_data:
            wav_set = set(blk_data['net_waive'])
        else:
            wav_set = set()

        # Get 2W2S NDR set
        ndr2x_set = set(['waive'])
        for ndr_name, ndr_data in def_info['ndr'].items():
            pass2x = True
            for layer, layer_data in ndr_data['layer'].items():
                if 'width' in layer_data and layer_data['width'] < unit2x:
                    pass2x = False
                    break
                if 'spacing' in layer_data and layer_data['spacing'] < unit2x:
                    pass2x = False
                    break
            if pass2x:
                ndr2x_set.add(ndr_name)

        # Net check
        check_2w2s = {'pass': 'PASS', 'path': []}
        net_info_dict = def_info['net']
        clk_len, path_len, rule_len = 0, 0, 0

        for clk_name, path_list in blk_data['clk'].items():
            if (size := len(clk_name)) > clk_len:
                clk_len = size

            for path in path_list:
                path_check = {
                    'pass': ['PASS', ''], 
                    'clk': clk_name,
                    'stp': (stp := (prefix + path['stp'])),
                    'edp': (edp := (prefix + path['edp'])),
                    'net': [],
                    'rule': (rule_dict := {}),
                    'ratio': 0.0,
                    'net_len': 0
                }

                if (size := len(stp)) > path_len:
                    path_len = size
                if (size := len(edp)) > path_len:
                    path_len = size
                net_len = path_len

                for net in path['net']:
                    net_info = net_info_dict[net]
                    ndr = net_info.get('ndr', None)
                    if ndr is None:
                        ndr = 'waive' if net in wav_set else 'default'
                    net_name = prefix + net
                    path_check['net'].append((net_name, ndr))

                    if ndr in rule_dict:
                        rule_dict[ndr] += 1
                    else:
                        rule_dict[ndr] = 1
                    if ndr in ndr2x_set:
                        path_check['ratio'] += 1
                    if (size := len(net_name)) > net_len:
                        net_len = size

                path_check['net_len'] = net_len
                path_check['ratio'] /= len(path_check['net'])
                if (ratio := path_check['ratio']) < config['pass_ratio']:
                    key = f'{stp}:{edp}'
                    if is_adj and ratio >= adj_dict.get(key, 100):
                        path_check['pass'][1] = '(W)'
                    else:
                        path_check['pass'][0] = 'FAIL'
                        check_2w2s['pass'] = 'FAIL'
                elif 'waive' in rule_dict:
                    path_check['pass'][1] = '(W)'
                check_2w2s['path'].append(path_check)

                size = max([len(x) + len(str(y)) for x, y in rule_dict.items()])
                if size > rule_len:
                    rule_len = size

        # Ouptut summary report
        result = check_2w2s['pass']
        id_len = len(str(len(check_2w2s['path'])))
        path_len += 2
        rule_len += 3

        id_len = 2 if id_len < 2 else id_len
        path_len = 4 if path_len < 4 else path_len
        rule_len = 9 if rule_len < 9 else rule_len

        print(file=out_fp)
        print('====== Block: {}, Result: {}'.format(blk, result), file=out_fp)
        print(file=out_fp)

        ## Print summary table
        title_list = ['ID', 'Check', 'Clk', 'Path', 'RouteRule', '2W2S Ratio']
        col_len = [id_len, 4, clk_len, path_len, rule_len, 7]
        for i, title in enumerate(title_list):
            if (size := len(title)) > col_len[i]:
                col_len[i] = size

        div = '+' + ''.join(['-{}-+'.format('-' * x) for x in col_len])
        fs = '|' + ''.join([' {{:{}s}} |'.format(x) for x in col_len])

        print('--- [Summary]', file=out_fp)
        print(div, file=out_fp)
        print(fs.format(*title_list), file=out_fp)
        print(div, file=out_fp)

        for i, path in enumerate(check_2w2s['path']):
            rule_list = [(x, y) for x, y in path['rule'].items()]
            print(fs.format(
                str(i), 
                path['pass'][0],
                path['clk'],
                'S:' + path['stp'],
                '{} ({})'.format(*rule_list[0]),
                '{:.2%}'.format(path['ratio'])
            ), file=out_fp)
            print(fs.format(
                '', 
                path['pass'][1],
                '', 
                'E:' + path['edp'], 
                '{} ({})'.format(*rule_list[1]) if len(rule_list) > 1 else '',
                ''
            ), file=out_fp)
            for rule in rule_list[2:]:
                print(fs.format('', '', '', '', '{} ({})'.format(*rule), ''),
                      file=out_fp)
            print(div, file=out_fp)

        print(file=out_fp)

        ## Print UNIT/DR/NDR
        print('--- [UNIT] : {}'.format(def_info['unit']['unit']), file=out_fp)
        print('--- [DR]   : {{W:{0:.3f},S:{0:.3f}}}'.format(config['unit']), 
              file=out_fp)

        for ndr_name, ndr_data in def_info['ndr'].items():
            print(file=out_fp)
            print('--- [NDR] {}: {{'.format(ndr_name), file=out_fp)
            cnt = 0
            for layer_name, layer_data in ndr_data['layer'].items():
                if cnt == 0:
                    print('{}'.format(' ' * 4), end='', file=out_fp)
                elif cnt == 4:
                    print('\n{}'.format(' ' * 4), end='', file=out_fp)
                    cnt = 0
                str_ = ''
                if 'width' in layer_data:
                    str_ += 'W:{:.3f},'.format(layer_data['width'] / dbu) 
                if 'spacing' in layer_data:
                    str_ += 'S:{:.3f},'.format(layer_data['spacing'] / dbu) 
                print('{}:{{{}}},'.format(layer_name, str_[:-1]), end='', 
                      file=out_fp)
                cnt += 1
            print('\n}}', file=out_fp)
        print(file=out_fp)

        ## Print clock path
        for i, path in enumerate(check_2w2s['path']):
            net_len = path['net_len']
            print('--- [PATH-{}]'.format(i), file=out_fp)
            print('S: {}    (startpoint)'.format(path['stp'].ljust(net_len)), 
                  file=out_fp)
            for net in path['net']:
                print('N: {}    ({})'.format(net[0].ljust(net_len), net[1]),
                      file=out_fp)
            print('E: {}    (endpoint)'.format(path['edp'].ljust(net_len)), 
                  file=out_fp)
            print(file=out_fp)

    if out_fpath is not None:
        out_fp.close()
    return check_2w2s['pass']


def _get_vio_zone(bnd_dict: dict, margin: float, is_inter: bool) -> list:
    vio_zone_list = []
    for xmin, xmax, ymin, _ in bnd_dict['t']:
        vio_zone_list.append((
            xmin - margin,
            xmax + margin,
            ymin - margin,
            ymin
        ))
    for xmin, xmax, ymin, _ in bnd_dict['b']:
        vio_zone_list.append((
            xmin - margin,
            xmax + margin,
            ymin,
            ymin + margin
        ))
    for xmin, _, ymin, ymax in bnd_dict['l']:
        vio_zone_list.append((
            xmin,
            xmin + margin,
            ymin - margin,
            ymax + margin
        ))
    for xmin, _, ymin, ymax in bnd_dict['r']:
        vio_zone_list.append((
            xmin - margin,
            xmin,
            ymin - margin,
            ymax + margin
        ))
    return vio_zone_list


def _check_net_keep_out(test_net_list: list, def_info: dict, unit: float, 
                        vio_zone_list: list, is_dbg: bool=False) -> list:
    unith2 = unit * def_info['unit']['percision'] / 2
    vio_net_list = []

    for net_name in test_net_list:
        net_data = def_info['net'][net_name]
        ndr_name = net_data.get('ndr', None)
        is_vio = False

        if is_dbg:  # for debug
            print('\n=== Net:', net_name)

        for route in net_data['route']:
            if ndr_name is not None:
                ndr = def_info['ndr'][ndr_name]
                off = ndr['layer'][route['layer']]['width'] / 2
            else:
                off = unith2

            for segment in route['segment']:
                if segment['type'] in {'rh', 'rv', 'rd'}:
                    xmin = segment['coor'][0] - off
                    xmax = segment['coor'][1] + off
                    ymin = segment['coor'][2] - off
                    ymax = segment['coor'][3] + off
                elif segment['type'] == 'vi':
                    xmin = segment['coor'][0] - off
                    xmax = segment['coor'][0] + off
                    ymin = segment['coor'][1] - off
                    ymax = segment['coor'][1] + off

                if is_dbg:  # for debug
                    print('\ntest_zone: ({:10.0f}, {:10.0f}, {:10.0f}, {:10.0f})'.format(
                        xmin, xmax, ymin, ymax))

                for vio_zone in vio_zone_list:
                    if is_dbg:  # for debug
                        print('vio_zone:  ({:10.0f}, {:10.0f}, {:10.0f}, {:10.0f})'.format(
                            *vio_zone))
                    xmin_hit = (xmin < vio_zone[1])
                    xmax_hit = (xmax > vio_zone[0])
                    ymin_hit = (ymin < vio_zone[3])
                    ymax_hit = (ymax > vio_zone[2])
                    if xmin_hit and xmax_hit and ymin_hit and ymax_hit:
                        if is_dbg:  # for debug
                            print('--- !!! VIOLATION !!!')
                        vio_net_list.append(net_name)
                        is_vio = True
                        break

                if is_vio:
                    break
            if is_vio:
                break

    return vio_net_list


def check_bnd_wire_out(out_fpath, config: dict, def_parser_dict: dict, 
                       is_dbg: bool=False) -> bool:
    """Boundary wire keep out check flow."""
    is_top = (config['type'] == 'top')
    out_fp = sys.stdout if out_fpath is None else open(out_fpath, 'w')
    check_pass = True

    for blk, blk_data in config['block'].items():
        def_info = def_parser_dict[blk].def_dict
        margin = config['margin'] * def_info['unit']['percision']
        prefix = f'{blk}/' if is_top else ''

        if is_dbg:  # for debug
            print('\n=== [Block: {}]'.format(blk))

        # Get the boundary violation zone
        vio_zone_list = _get_vio_zone(def_info['diearea'], margin, True)

        # Net check by the test zone
        vio_net_list = _check_net_keep_out(blk_data['net'], def_info, config['unit'], 
                                           vio_zone_list, is_dbg)

        if len(vio_net_list):
            result, check_pass = 'FAIL', False
        else:
            result = 'PASS'

        print(file=out_fp)
        print('====== Block: {}, Result: {}'.format(blk, result), file=out_fp)
        for vio_net in vio_net_list:
            print(file=out_fp)
            print('net:', vio_net, file=out_fp)
        print(file=out_fp)

    if out_fpath is not None:
        out_fp.close()
    return check_pass 


##############################################################################
### Main


def create_argparse() -> argparse.ArgumentParser:
    """Create an argument parser."""
    parser = argparse.ArgumentParser(
                formatter_class=argparse.RawTextHelpFormatter,
                description='Layout Check Tool')

    parser.add_argument('-clk_2w2s', dest='clk_2w2s_cfg', metavar='<json_file>', 
                        help='Configuration for the clock 2W2S check.') 
    parser.add_argument('-bound_wire_out', dest='bnd_wire_out_cfg', metavar='<json_file>', 
                        help='Configuration for the boundary wire keep out check.') 
    parser.add_argument('-macro_wire_out', dest='ma_wire_out_cfg', metavar='<json_file>', 
                        help='Configuration for the macro wire keep out check.') 
    parser.add_argument('-macro_cell_out', dest='ma_cell_out_cfg', metavar='<json_file>', 
                        help='Configuration for the macro cell keep out check.') 
    parser.add_argument('-outdir', dest='outdir', metavar='<directory>', 
                        help='Output report directory.') 
    parser.add_argument('-verbose', dest='is_verb', action='store_true', 
                              help="Print process message.")
    parser.add_argument('-debug', dest='is_dbg', action='store_true', 
                              help="Print debug message.")

    return parser


def main():
    """Main function."""
    parser = create_argparse()
    args = parser.parse_args()

    def_parser_dict, def_req_dict = {}, {}
    lef_set, macro_dict = set(), {}
    check_result = {}

    if args.outdir is not None:
        outdir = Path(args.outdir)
        if not outdir.exists():
            outdir.mkdir()

    def load_json(json_fpath, schema) -> dict:
        with open(json_fpath, 'r', encoding='utf-8') as json_fp:
            config = json.load(json_fp)
        try:
            validate(instance=config, schema=schema)
            return config
        except ValidationError as e:
            print(f'Error: JSON schema check fail ({json_fpath}).')
            print(e)
            exit(1)

    # Load the configuration of the clock 2W2S check
    if args.clk_2w2s_cfg is not None:
        config_2w2s = load_json(args.clk_2w2s_cfg, CLK_2W2S_SCHEMA)

        for blk, blk_data in config_2w2s['block'].items():
            def_parser = def_parser_dict.setdefault(blk, DEFParser(blk_data['def']))
            def_req = def_req_dict.setdefault(blk, {'comp': [], 'net': []})
            for path_list in blk_data['clk'].values():
                for path_data in path_list:
                    def_req['net'].extend(path_data['net'])

    # Load the configuration of the boundary wire keep out check
    if args.bnd_wire_out_cfg is not None:
        config_bnd_wire_out = load_json(args.bnd_wire_out_cfg, BOUND_WIRE_OUT_SCHEMA)

        for blk, blk_data in config_bnd_wire_out['block'].items():
            def_parser = def_parser_dict.setdefault(blk, DEFParser(blk_data['def']))
            def_req = def_req_dict.setdefault(blk, {'comp': [], 'net': []})
            def_req['net'].extend(blk_data['net'])

    # Load the configuration of the macro wire keep out check
    if args.ma_wire_out_cfg is not None:
        config_ma_wire_out = load_json(args.ma_wire_out_cfg, MACRO_WIRE_OUT_SCHEMA)
        lef_set.update(config_ma_wire_out['lefs'])

        for blk, blk_data in config_ma_wire_out['block'].items():
            def_parser = def_parser_dict.setdefault(blk, DEFParser(blk_data['def']))
            def_req = def_req_dict.setdefault(blk, {'comp': [], 'net': []})
            for macro_data in blk_data['macro']:
                def_req['net'].extend(macro_data['net'])

    # Load the configuration of the macro cell keep out check
    if args.ma_cell_out_cfg is not None:
        config_ma_cell_out = load_json(args.ma_cell_out_cfg, MACRO_CELL_OUT_SCHEMA)
        lef_set.update(config_ma_cell_out['lefs'])

        for blk, blk_data in config_ma_cell_out['block'].items():
            def_parser = def_parser_dict.setdefault(blk, DEFParser(blk_data['def']))
            def_req = def_req_dict.setdefault(blk, {'comp': [], 'net': []})
            for macro_data in blk_data['macro']:
                def_req['cell'].extend(macro_data['cell'])

    # Parsing LEF file
    if len(lef_set):
        lef_parser = LEFParser(list(lef_set))
        lef_parser.parse_lef()
        macro_dict = lef_parser.blk_dict
    if args.is_dbg:  # for debug
        if (len(lef_set)):
            print('\n[LEF Information]')
            print('\n', macro_dict)

    # Parsing DEF file
    for blk, def_parser in def_parser_dict.items():
        def_parser.parse_def(def_req_dict[blk])
    if args.is_dbg:  # for debug 
        print('\n[DEF Information]')
        for def_parser in def_parser_dict.values():
            def_parser.debug_print()

    # Clock 2W2S check flow
    if args.clk_2w2s_cfg is not None:
        out_fpath = None
        if args.outdir is not None:
            out_fpath = outdir / 'clock_2w2s_check.rpt'

        check_result['clk_2w2s'] = [
            'Clock 2W2S Check', 
            check_2w2s_flow(out_fpath, config_2w2s, def_parser_dict)
        ]

    # Boundary wire keep out check flow
    if args.bnd_wire_out_cfg is not None:
        out_fpath = None
        if args.outdir is not None:
            out_fpath = outdir / 'boundary_wire_keepout.rpt'
        if args.is_dbg:  # for debug
            print('\n[Bounday Wire Keep Out Check]')

        check_result['bnd_wire_out'] = [
            'Boundary Wire Keep Out',
            check_bnd_wire_out(
                out_fpath, 
                config_bnd_wire_out, 
                def_parser_dict,
                args.is_dbg
            )
        ]

    # Macro wire keep out check flow
    # import pdb; pdb.set_trace()

    # Macro cell keep out check flow

    if args.is_verb:
        item_len = max([len(x) for x, _ in check_result.values()])

        print('\n=== Layout Check Summary ===\n')
        for item, is_pass in check_result.values():
            print('{}: {}'.format(
                item.ljust(item_len), 
                'PASS' if is_pass else 'FAIL'
            ))
        print()

    # import pdb; pdb.set_trace()


if __name__ == '__main__':
    main()


