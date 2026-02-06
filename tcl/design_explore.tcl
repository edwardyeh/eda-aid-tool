set timing_report_unconstrained_paths true

### === Private Function

### === Common Function

### user procedure list (user_help_des)  {{{
set USER_HELP_DES [dict create]
echo "Information: Type 'user_help_des' to show user procedure list."

proc user_help_des { args } {
    global USER_HELP_DES
    parse_proc_arguments -args $args argsp

    set gid_len [string length [dict size $USER_HELP_DES]]

    echo ""
    ## only show group title
    if {[info exists argsp(-only_group)]} {
        set gid 0
        foreach {gname proc_list} $USER_HELP_DES {
            echo [format "=== (%${gid_len}d %s" $gid $gname]
            incr gid
        }
        echo ""
        return
    }

    ## get column length
    set gid     0
    set col_len 0
    foreach {gname proc_list} $USER_HELP_DES {
        if {[info exists argsp(-group)] && $argsp(-group) != $gid} { continue }
        foreach {fname comment} $proc_list {
            set newlen [string length $fname]
            if {$newlen > $col_len} { set col_len $newlen }
        }
        incr gid
    }

    ## show the procedure list
    set gid 0
    foreach {gname proc_list} $USER_HELP_DES {
        if {[info exists argsp(-group)] && $argsp(-group) != $gid} { continue }
        echo [format "=== (%${gid_len}d) %s\n" $gid $gname]
        foreach {fname comment} $proc_list {
            echo [format "  %-${col_len}s   %s" $fname $comment]
        }
        echo ""
        incr gid
    }
    echo ""
}

define_proc_attributes user_help_des -info "Show the user procedure list" \
    -define_args { \
        {-only_group "Only show group titles"                              ""  boolean optional}
        {-group      "Only show the user procedures of the specific group" gid int     optional}
    }
#}}}

### === Design Review

### explore design module (explore_design_module)  {{{
dict append USER_HELP_DES "Design Review" { explore_design_module "Explore design module" }

proc explore_design_module { args } {
    parse_proc_arguments -args $args argsp

    # option format:
    #   -group  [dict create re_pattern1 group_name1 re_pattern2 group_name2 ... ]
    #   -waive  [list cell1 cell2 ... ]

    set PART_REGEXP "^(chip_top\\w+)/.+$"
    set PART_FILTER "chip_top*"

    if {[info exists argsp(-top)]} {
        set MOD_FILTER "chip_top*/i_chip_core*/i_core*/i_*"
    } else {
        set MOD_FILTER "i_chip_core*/i_core*/i_*"
    }
    
    if {[info exists argsp(-config)]} {
        set config_dict $argsp(-config)
        if {[dict exists $config_dict PART_REGEXP]} {
            set PART_REGEXP [dict get $config_dict PART_REGEXP]
        }
        if {[dict exists $config_dict PART_FILTER]} {
            set PART_FILTER [dict get $config_dict PART_FILTER]
        }
        if {[dict exists $config_dict MOD_FILTER]} {
            set MOD_FILTER [dict get $config_dict MOD_FILTER]
        }
    }

    if {[info exists argsp(-group)]} {
        set group_dict $argsp(-group)
    } else {
        set group_dict {}
    }

    set mod_coll [get_cells -quiet $MOD_FILTER]
    if {[info exists argsp(-waive)]} {
        set mod_coll [remove_from_col $mod_coll [get_cells -quiet $argsp(-waive)]]
    }

    set PART_MOD_DICT [dict create]

    foreach_in_col mod_cell $mod_coll {
        set mod_name [get_object_name $mod_cell]
        set ref_name [get_attr $mod_cell ref_name]

        if {[info exists argsp(-top)]} {
            regexp "$PART_REGEXP" $mod_name -> part_name
        } else {
            set part_name "(none)"
        }

        if {[dict exists $PART_MOD_DICT $part_name]} {
            set part_dict [dict get $PART_MOD_DICT $part_name]
        } else {
            set part_dict [dict create]
        }

        set gname "(none)"
        dict for {pat gname_tmp} $group_dict {
            if {[regexp $pat $mod_name]} {
                set gname $gname_tmp
                break
            }
        }

        dict lappend part_dict $gname [list $mod_name $ref_name]
        dict set PART_MOD_DICT $part_name $part_dict
    }

    if {[info exists argsp(-print)] || [info exists argsp(-outfile)]} {
        if {[info exists argsp(-outfile)]} {
            set fid [open $argsp(-outfile) "w"]
        } else {
            set fid stdout
        }

        set fs   "%-55s %-30s"
        set head [format $fs "Instance" "Design"]
        set div1 [string repeat "=" [expr 55 + 30 + 1]]

        puts $fid ""
        dict for {part_name part_dict} $PART_MOD_DICT {
            puts $fid "====== $part_name"
            puts $fid $div1
            puts $fid $head
            puts $fid $div1
            if {[dict size $part_dict] > 1} {
                dict for {gname mod_list} $part_dict {
                    puts $fid "###### $gname ######"
                    foreach mod_info $mod_list {
                        puts $fid [format $fs [lindex $mod_info 0] [lindex $mod_info 1]]
                    }
                }
            } else {
                foreach mod_info [dict get $part_dict "(none)"] {
                    puts $fid [format $fs [lindex $mod_info 0] [lindex $mod_info 1]]
                }
            }
            puts $fid ""
            puts $fid ""
        }

        if {[info exists argsp(-outfile)]} {
            close  $fid
            return $PART_MOD_DICT
        }
    } else {
        return $PART_MOD_DICT
    }
}

define_proc_attributes explore_design_module -info "Explore design module" \
    -define_args { \
        {-top     "Explore from top"                ""          boolean optional}
        {-group   "Module group pattern dictionary" group_dict  list    optional}
        {-waive   "Module waive list"               waive_list  list    optional}
        {-print   "Show the result but no return"   ""          boolean optional}
        {-outfile "Dump the result and return"      filepath    string  optional}
        {-config  "User configuration dictionary"   config_dict list    optional}
    }
#}}}

### explore design sram (explore_design_sram)  {{{
dict append USER_HELP_DES "Design Review" { explore_design_sram "Explore design sram" }

proc explore_design_sram { args } {
    parse_proc_arguments -args $args argsp

    # option format:
    #   -mod_group  [dict create re_pattern1 group_name1 re_pattern2 group_name2 ... ]
    #   -clk_group  [dict create re_pattern1 group_name1 re_pattern2 group_name2 ... ]

    set PART_REGEXP "^(chip_top\\w+)/.+$"
    set PART_FILTER "chip_top*"

    if {[info exists argsp(-top)]} {
        set MOD_FILTER "chip_top*/i_chip_core*/i_core*/i_*"
        set MOD_WAIVE  {chip_top*/i_chip_core*/i_core*/i_cb_*}
    } else {
        set MOD_FILTER "i_chip_core*/i_core*/i_*"
        set MOD_WAIVE  {i_chip_core*/i_core*/i_cb_*}
    }

    if {[info exists argsp(-mod_group)]} {
        set mod_group_dict $argsp(-mod_group)
    } else {
        set mod_group_dict {}
    }

    if {[info exists argsp(-clk_group)]} {
        set clk_group_dict $argsp(-clk_group)
    } else {
        set clk_group_dict {}
    }

    if {[info exists argsp(-debug)]} {
        set is_debug 1
    } else {
        set is_debug 0
    }

    set mod_coll [get_cells -quiet $MOD_FILTER]
    set mod_coll [remove_from_col $mod_coll [get_cells -quiet $MOD_WAIVE]]

    set PART_MOD_DICT [dict create]
    set inst_col_len  0
    set ref_col_len   0

    foreach_in_col mod_cell $mod_coll {
        set mod_name [get_object_name $mod_cell]
        if {$is_debug} { echo $mod_name }

        if {[info exists argsp(-top)]} {
            regexp "$PART_REGEXP" $mod_name -> part_name
        } else {
            set part_name "(none)"
        }

        if {[dict exists $PART_MOD_DICT $part_name]} {
            set part_dict [dict get $PART_MOD_DICT $part_name]
        } else {
            set part_dict [dict create]
        }

        if {[info exists ::synopsys_program_name] && $::synopsys_program_name == "fc_shell"} {
            set sram_coll [filter_col [get_cells * -hier] "design_type==black_box && \
                                                           is_memory_cell==true && \
                                                           full_name=~${mod_name}/*"]
        } else {
            set sram_coll [filter_col [get_cells * -hier] "is_black_box==true && \
                                                           is_memory_cell==true && \
                                                           full_name=~${mod_name}/*"]
        }

        if {[sizeof_col $sram_coll] == 0} { continue }

        set sram_dict [dict create]
        foreach_in_col sram_cell $sram_coll {
            set sram_name     [get_object_name $sram_cell]
            set sram_ref_name [get_attr $sram_cell ref_name]

            dict set sram_dict $sram_name $sram_ref_name

            if {[set newlen [string length $sram_name]] > $inst_col_len} {
                set inst_col_len $newlen
            }

            if {[set newlen [string length $sram_ref_name]] > $ref_col_len} {
                set ref_col_len $newlen
            }
        }

        dict set part_dict $mod_name $sram_dict
        dict set PART_MOD_DICT $part_name $part_dict
    }

    if {[info exists argsp(-print)] || [info exists argsp(-outfile)]} {
        if {[info exists argsp(-outfile)]} {
            set fid [open $argsp(-outfile) "w"]
        } else {
            set fid stdout
        }

        set fs   "%-${inst_col_len}s    %-${ref_col_len}s    "
        set head [format $fs "Instance" "Cell"]
        set div1 [string repeat "=" [expr $inst_col_len + $ref_col_len + 8]]

        puts $fid ""
        dict for {part_name part_dict} $PART_MOD_DICT {
            set total_sram_count 0

            puts $fid [format "###### %s% s" $part_name [string repeat "#" [expr 52 - [string length $part_name]]]]
            puts $fid ""
            puts $fid ""
            dict for {mod_name sram_dict} $part_dict {
                set sram_count [dict size $sram_dict]
                set total_sram_count [expr $total_sram_count + $sram_count]

                puts $fid "====== $mod_name ($sram_count)"
                puts $fid $div1
                puts $fid $head
                puts $fid $div1
                dict for {sram_name sram_ref_name} $sram_dict {
                    puts $fid [format $fs $sram_name $sram_ref_name]
                }
                puts $fid ""
                puts $fid ""
            }
            puts $fid "=== Total SRAM number: $total_sram_count"
            puts $fid ""
            puts $fid ""
        }

        if {[info exists argsp(-outfile)]} {
            close  $fid
            return $PART_MOD_DICT
        }
    } else {
        return $PART_MOD_DICT
    }
}

define_proc_attributes explore_design_sram -info "Explore design sram" \
    -define_args { \
        {-top       "Explore from top"                ""         boolean optional}
        {-mod_group "Module group pattern dictionary" group_dict list    optional}
        {-clk_group "Clock group pattern dictionary"  group_dict list    optional}
        {-print     "Show the result but no return"   ""         boolean optional}
        {-outfile   "Dump the result and return"      filepath   string  optional}
        {-debug     "Show the debug information"      ""         boolean optional}
    }
#}}}

### report design module information (report_design_mod_info)  {{{
dict append USER_HELP_DES "Design Review" { report_design_mod_info "Report design module information" }

proc _print_design_mod_info { PART_NAME OUTPATH PART_MOD_DICT PART_MA_DICT } {
    #{{{
    redirect $OUTPATH {
        echo ""

        set fs   "%-55s %-30s"
        set head [format $fs "Instance" "Design"]
        set div1 [string repeat "=" [expr 55 + 30 + 1]]

        echo "###### Partition Moudle ####################################"
        echo ""
        echo "====== MODULE"
        echo $div1
        echo $head
        echo $div1
        if {[dict exists $PART_MOD_DICT $PART_NAME]} {
            set part_dict [dict get $PART_MOD_DICT $PART_NAME]
            if {[dict size $part_dict] > 1} {
                dict for {gname mod_list} $part_dict {
                    echo "###### $gname ######"
                    foreach mod_info $mod_list {
                        echo [format $fs [lindex $mod_info 0] [lindex $mod_info 1]]
                    }
                }
            } else {
                foreach mod_info [dict get $part_dict "(none)"] {
                    echo [format $fs [lindex $mod_info 0] [lindex $mod_info 1]]
                }
            }
        }
        echo ""
        echo ""

        echo "###### Partition Macro #####################################"
        echo ""
        echo "====== MACRO"
        echo $div1
        echo $head
        echo $div1
        if {[dict exists $PART_MA_DICT $PART_NAME]} {
            set part_dict [dict get $PART_MA_DICT $PART_NAME]
            if {[dict size $part_dict] > 1} {
                dict for {gname mod_list} $part_dict {
                    echo "###### $gname ######"
                    foreach mod_info $mod_list {
                        echo [format $fs [lindex $mod_info 0] [lindex $mod_info 1]]
                    }
                }
            } else {
                foreach mod_info [dict get $part_dict "(none)"] {
                    echo [format $fs [lindex $mod_info 0] [lindex $mod_info 1]]
                }
            }
        }
        echo ""
        echo ""
    }
    #}}}
}

proc report_design_mod_info { args } {
    parse_proc_arguments -args $args argsp

    # option format:
    #   -mod_group  [dict create re_pattern1 group_name1 re_pattern2 group_name2 ... ]
    #   -mod_waive  [list cell1 cell2 ... ]

    if {[info exists ::synopsys_program_name] && $::synopsys_program_name == "fc_shell"} {
        set design_name [get_attr [current_design] name]
    } else {
        set design_name [get_attr [current_design] full_name]
    }

    file delete -force $argsp(outdir)
    file mkdir $argsp(outdir)

    set extra_opt ""
    if {[info exists argsp(-top)]} {
        set extra_opt "-top $extra_opt"
    }
    
    ### Explore design module
    set cmd_opt "$extra_opt"
    if {[info exists argsp(-top)]} {
        set cmd_opt "-outfile ${argsp(outdir)}/${design_name}_design_info.rpt $cmd_opt"
    }

    if {[info exists argsp(-mod_group)]} {
        set cmd_opt "-group \$argsp(-mod_group) $cmd_opt"
    }

    if {[info exists argsp(-mod_waive)]} {
        set cmd_opt "-waive \$argsp(-mod_waive) $cmd_opt"
    }

    set PART_MOD_DICT [eval explore_design_module $cmd_opt]

    ### Explore design macro
    set cmd_opt "$extra_opt"
    if {[info exists argsp(-top)]} {
        set cmd_opt "-outfile ${argsp(outdir)}/${design_name}_macro_info.rpt $cmd_opt"
    }

    if {[info exists argsp(-ma_group)]} {
        set cmd_opt "-group \$argsp(-ma_group) $cmd_opt"
    }

    if {[info exists argsp(-ma_waive)]} {
        set cmd_opt "-waive \$argsp(-ma_waive) $cmd_opt"
    }

    if {[info exists argsp(-top)]} {
        set cmd_opt "-config {MOD_FILTER chip_top*/i_ip*/i_*} $cmd_opt"
    } else {
        set cmd_opt "-config {MOD_FILTER i_ip*/i_*} $cmd_opt"
    }

    set PART_MA_DICT [eval explore_design_module $cmd_opt]

    ### Print reports
    if {[info exists argsp(-top)]} {
        foreach part_name [get_object_name [get_cells chip_top*]] {
            set outpath "${argsp(outdir)}/${part_name}_info.rpt"
            _print_design_mod_info $part_name $outpath $PART_MOD_DICT $PART_MA_DICT
        }
    } else {
        set outpath "${argsp(outdir)}/partition_info.rpt"
        _print_design_mod_info "(none)" $outpath $PART_MOD_DICT $PART_MA_DICT
    }
}

define_proc_attributes report_design_mod_info -info "Report design module information" \
    -define_args { \
        { outdir    "Output directory"                path       string  required}
        {-top       "Explore from top"                ""         boolean optional}
        {-mod_group "Module group pattern dictionary" group_dict list    optional}
        {-mod_waive "Module waive list"               waive_list list    optional}
        {-ma_group  "Macro group pattern dictionary"  group_dict list    optional}
        {-ma_waive  "Macro waive list"                waive_list list    optional}
    }
#}}}

### explore design pads (explore_design_pads)  {{{
dict append USER_HELP_DES "Design Review" { explore_design_pads "Explore design PADs" }

proc _sort_inout_name { port_name_list } {
    #{{{
    ### Classification ###
    set group_dict   [dict create]
    set ungroup_list {}

    foreach port_name $port_name_list {
        # BT/DGPIO/PGPIO/ETH/MC
        if {[regexp {(BT|DGPIO|PGPIO|ETH|MC)(\d+)} $port_name -> tag i0]} {
            if {[dict exists $group_dict $tag]} {
                dict lappend group_dict $tag [list $port_name $i0]
            } else {
                dict set group_dict $tag [list [list $port_name $i0]]
            }
            continue
        }

        # CSI
        if {[regexp {(CSI)(\d+)*_(CK|D)(\d+)(N|P)} $port_name -> tag i0 i1 i2 i3]} {
            if {$i0 == ""  } { set i0 0 }
            if {$i1 == "CK"} { set i1 0 } else { set i1 1 }
            if {$i3 == "N" } { set i3 0 } else { set i3 1 }

            if {[dict exists $group_dict $tag]} {
                dict lappend group_dict $tag [list $port_name $i0 $i1 $i2 $i3]
            } else {
                dict set group_dict $tag [list [list $port_name $i0 $i1 $i2 $i3]]
            }
            continue
        }

        # HSI
        set tag "HSI"
        if {[regexp {(CLK|DATA)(N|P)(\d+)} $port_name -> i0 i1 i2]} {
            if {$i0 == "CLK"} { set i0 0 } else { set i0 1 }
            if {$i1 == "N"  } { set i1 0 } else { set i1 1 }

            if {[dict exists $group_dict $tag]} {
                dict lappend group_dict $tag [list $port_name $i0 $i1 $i2]
            } else {
                dict set group_dict $tag [list [list $port_name $i0 $i1 $i2]]
            }
            continue
        }

        # SEN
        if {[regexp {(SN)_(?:HD|VD|M|PX)(CLK)?} $port_name -> tag i0]} {
            if {$i0 == "CLK"} { set i0 0 } else { set i0 1 }

            if {[dict exists $group_dict $tag]} {
                dict lappend group_dict $tag [list $port_name $i0]
            } else {
                dict set group_dict $tag [list [list $port_name $i0]]
            }
            continue
        }

        # ungroup check
        set waive_list [get_object_name [get_ports -quiet { \
            PCIE_RSTN SYS_RST RESETN TCK TDI TDO TESTEN TMS TRST \
        }]]

        dict set group_dict $port_name [list [list $port_name]]
        if {[lsearch $waive_list $port_name] == -1} {
            lappend ungroup_list $port_name
        }
    }

    ### Reorder ###
    set order_list {}

    foreach plist [dict values $group_dict] {
        if {[llength $plist] == 1} {
            lappend order_list [lindex $plist 0 0]
        } else {
            set inum [expr [llength [lindex $plist 0]] - 1]

            for {set i $inum} {$i > 0} {incr i -1} {
                set plist [lsort -int -inc -index $i $plist]
            }

            foreach item $plist {
                lappend order_list [lindex $item 0]
            }
        }
    }

    if {[llength $ungroup_list] > 0} {
        echo "Information: Inout without sort: {$ungroup_list}"
    }
    return $order_list
    #}}}
}

proc explore_design_pads { args } {
    parse_proc_arguments -args $args argsp

    set PART_REGEXP "^(chip_top\\w+)/.+$"

    if {[info exists argsp(-top)]} {
        set PAD_FILTER "is_hierarchical==false && full_name=~chip_top*/i_ip*/u_*"
    } else {
        set PAD_FILTER "is_hierarchical==false && full_name=~i_ip*/u_*"
    }

    set PART_PAD_DICT [dict create]
    foreach_in_col port [get_ports * -quiet -filter "direction==inout"] {
        set pad_cell [get_cells -of [get_pins -of [get_nets -seg -of $port]] -filter $PAD_FILTER]

        if {[sizeof_col $pad_cell] > 0} {
            if {[info exists argsp(-top)]} {
                regexp $PART_REGEXP [get_object_name $pad_cell] -> part_name
            } else {
                set part_name "(none)"
            }
            set port_name [get_object_name $port]
            dict set PART_PAD_DICT $part_name $port_name $pad_cell
        }
    }

    if {[info exists argsp(-print)] || [info exists argsp(-outfile)]} {
        if {[info exists argsp(-outfile)]} {
            set fid [open $argsp(-outfile) "w"]
        } else {
            set fid stdout
        }

        set fs   "%-20s %-20s %-40s"
        set head [format $fs "Inout" "PadType" "Instance"]
        set div1 [string repeat "=" [expr 20 + 20 + 40 + 2]]

        puts $fid ""
        foreach part_name [lsort [dict keys $PART_PAD_DICT]] {
            set pad_dict [dict get $PART_PAD_DICT $part_name]
            puts $fid "====== $part_name"
            puts $fid $div1
            puts $fid $head
            puts $fid $div1
            set sort_list [_sort_inout_name [lsort [dict key $pad_dict]]]
            foreach port_name $sort_list {
                set pad_cell [dict get $pad_dict $port_name]
                puts $fid [format $fs \
                        $port_name \
                        [get_attr $pad_cell ref_name] \
                        [get_object_name $pad_cell] \
                     ]
            }
            puts $fid ""
            puts $fid ""
        }

        if {[info exists argsp(-outfile)]} {
            close  $fid
            return $PART_PAD_DICT
        }
    } else {
        return $PART_PAD_DICT
    }
}

define_proc_attributes explore_design_pads -info "Explore design PADs" \
    -define_args { \
        {-top     "Explore design from top"       ""       boolean optional}
        {-print   "Show the result but no return" ""       boolean optional}
        {-outfile "Dump the result and return"    filepath string  optional}
    }
#}}}

### explore design io (explore_design_io)  {{{
dict append USER_HELP_DES "Design Review" { explore_design_io "Explore design IO" }

proc _get_part_tag { part_name } {
    #{{{
    if {[regexp {chip_top_(\w+)} $part_name -> tag]} {
        return [string toupper $tag]
    } elseif {[regexp {chip_top(\d+)} $part_name -> tag]} {
        return "TOP${tag}"
    } else {
        return "NA"
    }
    #}}}
}

proc explore_design_io { args } {
    parse_proc_arguments -args $args argsp

    set PART_REGEXP "^(chip_top\\w+)/.+$"
    set PART_FILTER "chip_top*"

    # option format:
    #   -group [dict create group1 [dict create tag11 regexp11 ... ] ... ]
    #   -waive [list pin1 pin2 ... ]

    if {[info exists argsp(-group)]} {
        set group_dict $argsp(-group)
    } else {
        set group_dict {}
    }

    if {[info exists argsp(-top)]} {
        if {[info exists argsp(-waive)]} {
            set waive_coll [get_pins -quiet $argsp(-waive)]
        } else {
            set waive_coll {}
        }

        set io_dict [dict create]
        foreach_in_col part_cell [get_cells $PART_FILTER] {
            set pin_coll [remove_from_col [get_pins -of $part_cell] $waive_coll]
            dict set io_dict [get_object_name $part_cell] $pin_coll 
        }
    } else {
        if {[info exists argsp(-waive)]} {
            set waive_coll [get_ports -quiet $argsp(-waive)]
        } else {
            set waive_coll {}
        }

        set port_coll [remove_from_col [get_ports * -filter "direction!=inout"] $waive_coll]
        set io_dict   [dict create "(none)" $port_coll]
    }

    set IO_GROUP_DICT [dict create]

    dict for {part_name io_coll} $io_dict {
        set part_dict [dict create "(none)" {}]

        foreach_in_col io_obj $io_coll {
            set io_name [get_object_name $io_obj]
            set io_dir  [get_attr $io_obj direction]

            set io_type "unknown"
            if {[get_attr -quiet $io_obj is_clock_pin] == "true"} {
                set io_type "clock"
            } elseif {[get_attr -quiet $io_obj is_data_pin] == "true"} {
                set io_type "data"
            }

            if {$io_dir == "in"} {
                set dir2 "out"
            } else {
                set dir2 "in"
            }
            set io_coll2 [get_pins -quiet -of [get_nets -quiet -of $io_obj] -filter "direction==$dir2"]
            set io_obj2  [index_col $io_coll2 0]

            if {[sizeof_col $io_obj2] > 0} {
                regexp $PART_REGEXP [get_object_name $io_obj2] -> part_name2
            } else {
                set part_name2 ""
            }
            set io_conn "[_get_part_tag $part_name]:[_get_part_tag $part_name2]"

            set gname "(none)"
            dict for {gname_tmp tag_dict} $group_dict {
                dict for {tname pat} $tag_dict {
                    if {[regexp $pat $io_name]} {
                        set gname $gname_tmp

                        if {[dict exists $part_dict $gname]} {
                            set g_info_dict [dict get $part_dict $gname]
                        } else {
                            set g_info_dict [dict create]
                        }

                        dict lappend g_info_dict $tname [list $io_name $io_dir $io_type $io_conn]
                        dict set part_dict $gname $g_info_dict
                        break
                    }
                }

                if {$gname != "(none)"} {
                    break
                }
            }

            if {$gname == "(none)"} {
                dict lappend part_dict "(none)" [list $io_name $io_dir $io_type $io_conn]
            }
        }

        dict set IO_GROUP_DICT $part_name $part_dict
    }

    if {[info exists argsp(-print)] || [info exists argsp(-outfile)]} {
        if {[info exists argsp(-outfile)]} {
            set fid [open $argsp(-outfile) "w"]
        } else {
            set fid stdout
        }

        set fs   "%-55s %-11s %-11s %-11s %-11s"
        set head [format $fs "TagName" "Direction" "Type" "Connect" "Count"]
        set div1 [string repeat "=" [expr 55 + 12 * 4]]

        puts $fid ""
        dict for {part_name part_dict} $IO_GROUP_DICT {
            puts $fid [format "###### %s %s" $part_name [string repeat "#" [expr 52 - [string length $part_name]]]]
            puts $fid ""
            foreach gname [dict key $part_dict] {
                if {$gname != "(none)"} {
                    puts $fid "====== $gname"
                    puts $fid $div1
                    puts $fid $head
                    puts $fid $div1
                    foreach {tname tag_info_list} [dict get $part_dict $gname] {
                        set tag_dir ""
                        foreach tag_info $tag_info_list {
                            lassign $tag_info io_name io_dir io_type io_conn
                            if {$tag_dir == ""} {
                                set tag_dir $io_dir
                            } elseif {$tag_dir != $io_dir} {
                                set tag_dir "mix"
                                break
                            }
                        }

                        set tag_type ""
                        foreach tag_info $tag_info_list {
                            lassign $tag_info io_name io_dir io_type io_conn
                            if {$tag_type == ""} {
                                set tag_type $io_type
                            } elseif {$tag_type != $io_type} {
                                set tag_type "mix"
                                break
                            }
                        }

                        set tag_conn ""
                        foreach tag_info $tag_info_list {
                            lassign $tag_info io_name io_dir io_type io_conn
                            if {$tag_conn == ""} {
                                set tag_conn $io_conn
                            } elseif {$tag_conn != $io_conn} {
                                set tag_conn "mix"
                                break
                            }
                        }

                        set io_cnt [llength $tag_info_list]
                        puts $fid [format $fs $tname $tag_dir $tag_type $tag_conn $io_cnt]
                    }
                    puts $fid ""
                } elseif {[llength [dict get $part_dict "(none)"]] > 0} {
                    puts $fid "====== NoGroup"
                    puts $fid $div1
                    puts $fid $head
                    puts $fid $div1
                    foreach io_info [dict get $part_dict "(none)"] {
                        lassign $io_info io_name io_dir io_type io_conn
                        puts $fid [format $fs $io_name $io_dir $io_type $io_conn 1]
                    }
                    puts $fid ""
                }
            }
            puts $fid ""
        }

        if {[info exists argsp(-outfile)]} {
            close  $fid
            return $IO_GROUP_DICT
        }
    } else {
        return $IO_GROUP_DICT
    }
}

define_proc_attributes explore_design_io -info "Explore design IO" \
    -define_args { \
        {-top     "Explore from top"                  ""         boolean optional}
        {-group   "Pin/Port group pattern dictionary" group_dict list    optional}
        {-waive   "Pin/Port waive list"               waive_list list    optional}
        {-print   "Show the result but no return"     ""         boolean optional}
        {-outfile "Dump the result and return"        filepath   string  optional}
    }
#}}}

### report design io information (report_design_io_info)  {{{
dict append USER_HELP_DES "Design Review" { report_design_io_info "Report design io information" }

proc report_design_io_info { args } {
    parse_proc_arguments -args $args argsp

    # option format:
    #   -io_group  [dict create group1 [dict create tag11 regexp11 ... ] ... ]
    #   -io_waive  [list pin1 pin2 ... ]

    if {[info exists ::synopsys_program_name] && $::synopsys_program_name == "fc_shell"} {
        set design_name [get_attr [current_design] name]
    } else {
        set design_name [get_attr [current_design] full_name]
    }

    file delete -force $argsp(outdir)
    file mkdir $argsp(outdir)

    set extra_opt ""
    if {[info exists argsp(-top)]} {
        set extra_opt "-top $extra_opt"
        set PART_LIST [get_object_name [get_cells chip_top*]]
    }
    
    ### Explore design pads
    set cmd_opt "$extra_opt"
    if {[info exists argsp(-top)]} {
        set cmd_opt "-outfile ${argsp(outdir)}/${design_name}_pad_info.rpt $cmd_opt"
    }

    set PART_PAD_DICT [eval explore_design_pads $cmd_opt]

    ### Explore design io
    set cmd_opt "$extra_opt"
    if {[info exists argsp(-top)]} {
        set cmd_opt "-outfile ${argsp(outdir)}/${design_name}_io_info.rpt $cmd_opt"
    }

    if {[info exists argsp(-io_group)]} {
        set cmd_opt "-group \$argsp(-io_group) $cmd_opt"
    }

    if {[info exists argsp(-io_waive)]} {
        set cmd_opt "-waive \$argsp(-io_waive) $cmd_opt"
    }

    set IO_GROUP_DICT [eval explore_design_io $cmd_opt]
    
    ### Print reports
    if {[info exists argsp(-top)]} {
        foreach part_name $PART_LIST {
            set outpath "${argsp(outdir)}/${part_name}_info.rpt"
            _print_design_io_info $part_name $outpath $PART_PAD_DICT $IO_GROUP_DICT
        }
    } else {
        set outpath "${argsp(outdir)}/partition_info.rpt"
        _print_design_io_info "(none)" $outpath $PART_PAD_DICT $IO_GROUP_DICT
    }
}

define_proc_attributes report_design_io_info -info "Report design io information" \
    -define_args { \
        { outdir    "Output directory"                  path       string  required}
        {-top       "Explore design from top"           ""         boolean optional}
        {-io_group  "Pin/Port group pattern dictionary" group_dict list    optional}
        {-io_waive  "Pin/Port waive list"               waive_list list    optional}
    }

proc _print_design_io_info { PART_NAME OUTPATH PART_PAD_DICT IO_GROUP_DICT } {
    #{{{
    redirect $OUTPATH {
        echo ""

        echo "###### Partition Inout #####################################"
        echo ""
        echo "====== IO/PAD"
        echo [format "%-20s %-20s %-55s" "Inout" "PadType" "Instance"]
        echo [string repeat "=" [expr 20 + 21 + 56]]
        if {[dict exists $PART_PAD_DICT $PART_NAME]} {
            set pad_dict  [dict get $PART_PAD_DICT $PART_NAME]
            set sort_list [_sort_inout_name [lsort [dict key $pad_dict]]]
            foreach port_name $sort_list {
                set pad_cell [dict get $pad_dict $port_name]
                echo [format "%-20s %-20s %-55s" \
                        $port_name \
                        [get_attr $pad_cell ref_name] \
                        [get_object_name $pad_cell] \
                     ]
            }
        }
        echo ""
        echo ""

        echo "###### Partition Input/Output ##############################"
        echo ""
        echo "====== Inter-Partition IO ======"
        echo ""
        if {[dict exists $IO_GROUP_DICT $PART_NAME]} {
            set part_dict [dict get $IO_GROUP_DICT $PART_NAME]
            foreach gname [dict key [dict get $IO_GROUP_DICT $PART_NAME]] {
                if {$gname != "(none)"} {
                    echo "====== $gname"
                    echo [format "%-55s %-11s %-11s %-11s %-11s" "TagName" "Direction" "Type" "Connect" "Count"]
                    echo [string repeat "=" [expr 55 + 12 * 4]]
                    foreach {tname tag_info_list} [dict get $part_dict $gname] {
                        set tag_dir ""
                        foreach tag_info $tag_info_list {
                            lassign $tag_info io_name io_dir io_type io_conn
                            if {$tag_dir == ""} {
                                set tag_dir $io_dir
                            } elseif {$tag_dir != $io_dir} {
                                set tag_dir "mix"
                                break
                            }
                        }

                        set tag_type ""
                        foreach tag_info $tag_info_list {
                            lassign $tag_info io_name io_dir io_type io_conn
                            if {$tag_type == ""} {
                                set tag_type $io_type
                            } elseif {$tag_type != $io_type} {
                                set tag_type "mix"
                                break
                            }
                        }

                        set tag_conn ""
                        foreach tag_info $tag_info_list {
                            lassign $tag_info io_name io_dir io_type io_conn
                            if {$tag_conn == ""} {
                                set tag_conn $io_conn
                            } elseif {$tag_conn != $io_conn} {
                                set tag_conn "mix"
                                break
                            }
                        }

                        set io_cnt [llength $tag_info_list]
                        echo [format "%-55s %-11s %-11s %-11s %-11s" $tname $tag_dir $tag_type $tag_conn $io_cnt]
                    }
                    echo ""
                } elseif {[llength [dict get $part_dict "(none)"]] > 0} {
                    echo "====== NoGroup"
                    echo [format "%-55s %-11s %-11s %-11s %-11s" "TagName" "Direction" "Type" "Connect" "Count"]
                    echo [string repeat "=" [expr 55 + 12 * 4]]
                    foreach io_info [dict get $part_dict "(none)"] {
                        lassign $io_info io_name io_dir io_type io_conn
                        echo [format "%-55s %-11s %-11s %-11s %-11s" $io_name $io_dir $io_type $io_conn 1]
                    }
                    echo ""
                }
            }
        }
        echo ""
    }
    #}}}
}
#}}}

### === Design Floorplan

### create group bound (create_group_bound)  {{{
dict append USER_HELP_DES "Common Function" { create_group_bound "Create group bound" }

proc create_group_bound { args } {
    parse_proc_arguments -args $args argsp
}

define_proc_attributes create_group_bound -info "Create group bound" \
    -define_args { \
        { group_dict  "Group dictionary"                                 group_dict list    required}
        {-top         "Explore from top"                                 ""         boolean optional}
        {-part_filter "Custom filter to get the partition cell (regexp)" expression string  optional}
        {-print "Show the result (default: log type)"                    type       one_of_string \
            { optional value_help {values {"log" "prc"}} }}
    }
#}}}

