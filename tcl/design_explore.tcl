set timing_report_unconstrained_paths true

### === Private Function

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

### === Common Function

### explore design pads (explore_design_pads)  {{{
dict append USER_HELP_DES "Common Function" { explore_design_pads "Explore design PADs" }

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

    if {[info exists argsp(-print)]} {
        echo ""
        foreach part_name [lsort [dict keys $PART_PAD_DICT]] {
            set pad_dict [dict get $PART_PAD_DICT $part_name]
            echo "====== $part_name"
            echo [format "%-20s %-20s %-60s" "Inout" "PadType" "Instance"]
            echo [string repeat "=" [expr 20 + 20 + 60]]
            foreach port_name [lsort [dict key $pad_dict]] {
                set pad_cell [dict get $pad_dict $port_name]
                echo [format "%-20s %-20s %-60s" \
                        $port_name \
                        [get_attr $pad_cell ref_name] \
                        [get_object_name $pad_cell] \
                     ]
            }
            echo ""
            echo ""
        }
    } else {
        return $PART_PAD_DICT
    }
}

define_proc_attributes explore_design_pads -info "Explore design PADs" \
    -define_args { \
        {-top   "Explore design from top" "" boolean optional}
        {-print "Show the result"         "" boolean optional}
    }
#}}}

### explore design module (explore_design_module)  {{{
dict append USER_HELP_DES "Common Function" { explore_design_module "Explore design module" }

proc explore_design_module { args } {
    parse_proc_arguments -args $args argsp

    set PART_REGEXP "^(chip_top\\w+)/.+$"
    set PART_FILTER "chip_top*"
    set MOD_FILTER  "chip_top*/i_chip_core*/i_core*/i_*"

    if {[info exists argsp(-waive)]} {
        set waive_coll [get_cells -quiet $argsp(-waive)]
    } else {
        set waive_coll {}
    }

    set mod_coll [get_cells -quiet $MOD_FILTER]

    set PART_MOD_DICT [dict create]
    foreach_in_col mod_cell $mod_coll {
        set mod_name [get_object_name $mod_cell]

        if {[sizeof_col [remove_from_col -inter $waive_coll $mod_cell]] == 0} {
            if {[info exists argsp(-top)]} {
                regexp "$PART_REGEXP" $mod_name -> part_name
            } else {
                set part_name "(none)"
            }

            if {[dict exists $PART_MOD_DICT $part_name]} {
                set tmp_coll [dict get $PART_MOD_DICT $part_name]
                dict set PART_MOD_DICT $part_name [add_to_col $tmp_coll $mod_cell]
            } else {
                dict set PART_MOD_DICT $part_name $mod_cell
            }
        }
    }

    if {[info exists argsp(-print)]} {
        echo ""
        dict for {part_name mod_coll} $PART_MOD_DICT {
            echo "====== $part_name"
            echo [format "%-60s %-20s" "Instance" "Design"]
            echo [string repeat "=" [expr 60 + 20]]
            foreach_in_col mod_cell $mod_coll {
                echo [format "%-60s %-20s" [get_object_name $mod_cell] [get_attr $mod_cell ref_name]]
            }
            echo ""
            echo ""
        }
    } else {
        return $PART_MOD_DICT
    }
}

define_proc_attributes explore_design_module -info "Explore design module" \
    -define_args { \
        {-top   "Explore from top"  ""         boolean optional}
        {-waive "Module waive list" waive_list list    optional}
        {-print "Show the result"   ""         boolean optional}
    }
#}}}

### explore design io (explore_design_io)  {{{
dict append USER_HELP_DES "Common Function" { explore_design_io "Explore design IO" }

proc explore_design_io { args } {
    parse_proc_arguments -args $args argsp

    set PART_REGEXP "^(chip_top\\w+)/.+$"
    set PART_FILTER "chip_top*"

    # format: { \
    #   group1 {tag11 regexp11 tag12 regexp12 ... } \
    #   group2 {tag21 regexp21 tag22 regexp22 ... } \
    #   ...
    # }
    if {[info exists argsp(-group)]} {
        set group_dict $argsp(-group)
    } else {
        set group_dict {}
    }

    set waive_coll {}
    if {[info exists argsp(-top)]} {
        if {[info exists argsp(-waive)]} {
            set waive_coll [get_pins -quiet $argsp(-waive)]
        }

        set io_dict [dict create]
        foreach_in_col part_cell [get_cells $PART_FILTER] {
            set pin_coll [remove_from_col [get_pins -of $part_cell] $waive_coll]
            dict set io_dict [get_object_name $part_cell] $pin_coll 
        }
    } else {
        if {[info exists argsp(-waive)]} {
            set waive_coll [get_ports -quiet $argsp(-waive)]
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

                        dict lappend g_info_dict $tname [list $io_name $io_dir $io_type]
                        dict set part_dict $gname $g_info_dict
                        break
                    }
                }

                if {$gname != "(none)"} {
                    break
                }
            }

            if {$gname == "(none)"} {
                dict lappend part_dict "(none)" [list $io_name $io_dir $io_type]
            }
        }

        dict set IO_GROUP_DICT $part_name $part_dict
    }

    if {[info exists argsp(-print)]} {
        echo ""
        dict for {part_name part_dict} $IO_GROUP_DICT {
            echo "====== $part_name ======"
            echo ""
            foreach gname [dict key $part_dict] {
                if {$gname != "(none)"} {
                    echo "====== $gname"
                    echo [format "%-60s %-20s %-20s" "TagName" "Direction" "Type"]
                    echo [string repeat "=" [expr 60 + 20 + 20]]
                    foreach {tname tag_info_list} [dict get $part_dict $gname] {
                        set tag_dir ""
                        foreach tag_info $tag_info_list {
                            lassign $tag_info io_name io_dir io_type
                            if {$tag_dir == ""} {
                                set tag_dir $io_dir
                            } elseif {$tag_dir != $io_dir} {
                                set tag_dir "mix"
                                break
                            }
                        }

                        set tag_type ""
                        foreach tag_info $tag_info_list {
                            lassign $tag_info io_name io_dir io_type
                            if {$tag_type == ""} {
                                set tag_type $io_type
                            } elseif {$tag_type != $io_type} {
                                set tag_type "mix"
                                break
                            }
                        }

                        echo [format "%-60s %-20s %-20s" $tname $tag_dir $tag_type]
                    }
                    echo ""
                } else {
                    echo "====== NoGroup"
                    echo [format "%-60s %-20s %-20s" "Pin/Port" "Direction" "Type"]
                    echo [string repeat "=" [expr 60 + 20 + 20]]
                    foreach io_info [dict get $part_dict "(none)"] {
                        lassign $io_info io_name io_dir io_type
                        echo [format "%-60s %-20s %-20s" $io_name $io_dir $io_type]
                    }
                    echo ""
                }
            }
            echo ""
        }
    } else {
        return $IO_GROUP_DICT
    }
}

define_proc_attributes explore_design_io -info "Explore design IO" \
    -define_args { \
        {-top   "Explore from top"                                 ""         boolean optional}
        {-waive "Pin/Port waive list"                              waive_list list    optional}
        {-group "Group constraint for the pin/port classification" group_dict list    optional}
        {-print "Show the result"                                  ""         boolean optional}
    }
#}}}

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

### report partition information (report_partition_info)  {{{
dict append USER_HELP_DES "Common Function" { report_partition_info "Report partition information" }

proc report_partition_info { args } {
    parse_proc_arguments -args $args argsp

    set PART_LIST [get_object_name [get_cells chip_top*]]

    set extra_opt ""
    if {[info exists argsp(-top)]} {
        set extra_opt "-top $extra_opt"
    }
    
    ### Expore design pads
    set PART_PAD_DICT [eval explore_design_pads $extra_opt]

    ### Expore design module
    set cmd_opt $extra_opt

    if {[info exists argsp(-mod_waive)]} {
        set cmd_opt "-waive \$argsp(-mod_waive) $cmd_opt"
    }

    set PART_MOD_DICT [eval explore_design_module $cmd_opt]

    ### Export design io
    set cmd_opt $extra_opt

    if {[info exists argsp(-io_waive)]} {
        set cmd_opt "-waive \$argsp(-io_waive) $cmd_opt"
    }

    # format: { \
    #   group1 {tag11 regexp11 tag12 regexp12 ... } \
    #   group2 {tag21 regexp21 tag22 regexp22 ... } \
    #   ...
    # }
    if {[info exists argsp(-io_group)]} {
        set cmd_opt "-group \$argsp(-io_group) $cmd_opt"
    }

    set IO_GROUP_DICT [eval explore_design_io $cmd_opt]
    
    ### Print reports
    file delete -force $argsp(outdir)
    file mkdir $argsp(outdir)

    if {[info exists argsp(-top)]} {
        foreach part_name $PART_LIST {
            set outpath "${argsp(outdir)}/${part_name}_info.rpt"
            _print_part_info $part_name $outpath $PART_PAD_DICT $PART_MOD_DICT $IO_GROUP_DICT
        }
    } else {
        set outpath "${argsp(outdir)}/partition_info.rpt"
        _print_part_info "(none)" $outpath $PART_PAD_DICT $PART_MOD_DICT $IO_GROUP_DICT
    }
}

define_proc_attributes report_partition_info -info "Report partition information" \
    -define_args { \
        {outdir     "Output directory"                                 path       string  required}
        {-top       "Explore from top"                                 ""         boolean optional}
        {-mod_waive "Module waive list"                                waive_list list    optional}
        {-io_waive  "Pin/Port waive list"                              waive_list list    optional}
        {-io_group  "Group constraint for the pin/port classification" group_dict list    optional}
    }

proc _print_part_info { PART_NAME OUTPATH PART_PAD_DICT PART_MOD_DICT IO_GROUP_DICT} {
    redirect $OUTPATH {
        echo ""

        echo "====== IO/PAD"
        echo [format "%-20s %-20s %-60s" "Inout" "PadType" "Instance"]
        echo [string repeat "=" 100]
        if {[dict exists $PART_PAD_DICT $PART_NAME]} {
            set pad_dict [dict get $PART_PAD_DICT $PART_NAME]
            foreach port_name [lsort [dict key $pad_dict]] {
                set pad_cell [dict get $pad_dict $port_name]
                echo [format "%-20s %-20s %-60s" \
                        $port_name \
                        [get_attr $pad_cell ref_name] \
                        [get_object_name $pad_cell] \
                     ]
            }
        }
        echo ""
        echo ""

        echo "====== MODULE"
        echo [format "%-60s %-20s" "Instance" "Design"]
        echo [string repeat "=" 100]
        if {[dict exists $PART_MOD_DICT $PART_NAME]} {
            set mod_coll [dict get $PART_MOD_DICT $PART_NAME]
            foreach_in_col mod_cell $mod_coll {
                echo [format "%-60s %-20s" [get_object_name $mod_cell] [get_attr $mod_cell ref_name]]
            }
        }
        echo ""
        echo ""

        echo "====== Inter-Partition IO ======"
        echo ""
        if {[dict exists $IO_GROUP_DICT $PART_NAME]} {
            set part_dict [dict get $IO_GROUP_DICT $PART_NAME]
            foreach gname [dict key [dict get $IO_GROUP_DICT $PART_NAME]] {
                if {$gname != "(none)"} {
                    echo "====== $gname"
                    echo [format "%-60s %-20s %-20s" "TagName" "Direction" "Type"]
                    echo [string repeat "=" 100]
                    foreach {tname tag_info_list} [dict get $part_dict $gname] {
                        set tag_dir ""
                        foreach tag_info $tag_info_list {
                            lassign $tag_info io_name io_dir io_type
                            if {$tag_dir == ""} {
                                set tag_dir $io_dir
                            } elseif {$tag_dir != $io_dir} {
                                set tag_dir "mix"
                                break
                            }
                        }

                        set tag_type ""
                        foreach tag_info $tag_info_list {
                            lassign $tag_info io_name io_dir io_type
                            if {$tag_type == ""} {
                                set tag_type $io_type
                            } elseif {$tag_type != $io_type} {
                                set tag_type "mix"
                                break
                            }
                        }

                        echo [format "%-60s %-20s %-20s" $tname $tag_dir $tag_type]
                    }
                    echo ""
                } else {
                    echo "====== NoGroup"
                    echo [format "%-60s %-20s %-20s" "TagName" "Direction" "Type"]
                    echo [string repeat "=" 100]
                    foreach io_info [dict get $part_dict "(none)"] {
                        lassign $io_info io_name io_dir io_type
                        echo [format "%-60s %-20s %-20s" $io_name $io_dir $io_type]
                    }
                    echo ""
                }
            }
        }
        echo ""
    }
}
#}}}

### === Top

### === Partition

