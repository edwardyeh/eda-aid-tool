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

define_proc_attributes user_help -info "Show the user procedure list" \
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

    if {[info exists argsp(-part_filter)]} {
        set PART_FILTER "^${argsp(-part_filter)}$"
    } else {
        set PART_FILTER "^(chip_top\w+)/.+$"
    }

    if {[info exists argsp(-pad_filter)]} {
        set PAD_FILTER $argsp(-pad_filter)
    } elseif {[info exists argsp(-top)]} {
        set PAD_FILTER "is_hierarchical==false && full_name=~chip_top\w+/i_ip\w+/u_\w+"
    } else {
        set PAD_FILTER "is_hierarchical==false && full_name=~i_ip\w+/u_\w+"
    }

    set PART_PAD_DICT [dict create]
    foreach_in_col port [get_ports * -quiet -filter "direction==inout"] {
        set pad_cell [filter_col [get_cells -of [get_pins -of [get_nets -seg -of $port]]] \
                                 -regexp "$PAD_FILTER"]

        if {[sizeof_col $pad_cell] > 0} {
            if {[info exists argsp(-top)]} {
                regexp "$PART_FILTER" [get_object_name $pad_cell] -> part_name
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
            echo [format "%-20s %-20s %-60s" "Port" "PadType" "Instance"]
            echo [string repeat "=" [expr 20 + 20 + 60]]
            foreach port_name [lsort [dict key $pad_dict]] {
                set pad_cell [dict get $pad_dict $port_name]
                echo [format "%-20s %-20s %-60s" \
                        $port_name \
                        [get_attr $pad_cell ref_name] \
                        [get_object_name $pad_cell] \
                     ]
            }
            echo "\n"
        }
    }
    return $PART_PAD_DICT
}

define_proc_attributes explore_design_pads -info "Explore design PADs" \
    -define_args { \
        {-top         "Explore design from top"                          ""         boolean optional}
        {-part_filter "Custom filter to get the partition cell (regexp)" expression string  optional}
        {-pad_filter  "Custom filter to get the PAD cell       (regexp)" expression string  optional}
        {-print       "Show the result"                                  ""         boolean optional}
    }
#}}}

### explore design module (explore_design_module)  {{{
dict append USER_HELP_DES "Common Function" { explore_design_module "Explore design module" }

proc explore_design_module { args } {
    parse_proc_arguments -args $args argsp

    if {[info exists argsp(-part_filter)]} {
        set PART_FILTER "^${argsp(-part_filter)}$"
    } else {
        set PART_FILTER "^chip_top\w+$"
    }

    # format: {<regexp pattern> ... }
    if {[info exists argsp(-waive)]} {
        set WAIVE_LIST $argsp(-waive)
    } else {
        set WAIVE_LIST []
    }

    if {[info exists argsp(-top)]} {
        if {[info exists argsp(-part_filter)]} {
            set part_coll [filter_col [get_cells * -hier] -regexp $PART_FILTER]
        } else {
            set part_coll [get_cells chip_top*]
        }
        set PART_LIST [lsort [get_object_name $part_coll]]
    } else {
        set PART_LIST {"(none)"}
    }

    if {[info exists argsp(-mod_filter)]} {
        set mod_coll [filter_col [get_cells * -hier] -regexp "${argsp(-mod_filter)}"]
    } else {
        set mod_coll [get_cells -quiet chip_top*/i_chip_core*/i_core*/i_*]
    }

    set PART_MOD_DICT [dict create]
    foreach_in_col mod_obj $mod_coll {
        set mod_name [get_object_name $mod_obj]

        set hit 0
        foreach waive_pat $WAIVE_LIST {
            if {[regexp "$waive_pat" $mod_name]} {
                set hit 1
                break
            }
        }

        if {$hit} {
            if {[info exists argsp(-top)]} {
                regexp "$PART_FILTER" [get_object_name $mod_obj] -> part_name
            } else {
                set part_name "(none)"
            }
            dict lappend $PART_MOD_DICT $part_name $mod_obj
        }
    }

    if {[info exists argsp(-print)]} {
        echo ""
        dict for {part_name mod_list} $PART_MOD_DICT {
            echo "====== $part_name"
            echo [format "%-60s %-20s" "Instance" "Design"]
            echo [string repeat "=" [expr 60 + 20]]
            foreach mod_obj $mod_list {
                echo [format "%-60s %-20s" [get_object_name $mod_obj] [get_attr $mod_obj ref_name]]
            }
            echo "\n"
        }
    }
    return $PART_MOD_DICT
}

define_proc_attributes explore_design_module -info "Explore design module" \
    -define_args { \
        {-top         "Explore from top"                                 ""         boolean optional}
        {-part_filter "Custom filter to get the partition cell (regexp)" expression string  optional}
        {-mod_filter  "Custom filter to get the design module (regexp)"  expression string  optional}
        {-waive       "Waive constraint (regexp)"                        list       list    optional}
        {-print       "Show the result"                                  ""         boolean optional}
    }
#}}}

### explore design io (explore_design_io)  {{{
dict append USER_HELP_DES "Common Function" { explore_design_io "Explore design IO" }

proc explore_design_io { args } {
    parse_proc_arguments -args $args argsp

    if {[info exists argsp(-part_filter)]} {
        set PART_FILTER "^${argsp(-part_filter)}$"
    } else {
        set PART_FILTER "^chip_top\w+$"
    }

    # format: {<group_name> <regexp_pattern> ... }
    if {[info exists argsp(-group)]} {
        set GROUP_DICT $argsp(-group)
    } else {
        set GROUP_DICT {}
    }

    set WAIVE_COLL {}
    if {[info exists argsp(-top)]} {
        if {[info exists argsp(-waive)]} {
            set WAIVE_COLL [get_pins -quiet $argsp(-waive)]
        }

        set io_dict [dict create]
        foreach_in_col part_cell [filter [get_cells * -hier] -regexp $PART_FILTER] {
            set pin_coll [remove_from_col [get_pins -of $part_cell] $WAIVE_COLL]
            dict set io_dict [get_object_name $part_cell] $pin_coll 
        }
    } else {
        if {[info exists argsp(-waive)]} {
            set WAIVE_COLL [get_ports -quiet $argsp(-waive)]
        }
        set port_coll [remove_from_col [get_ports * -filter "direction!=inout"] $WAIVE_COLL]
        set io_dict [dict create "(none)" $port_coll]
    }

    set IO_GROUP_DICT [dict create]
    dict for {part_name io_coll} $io_dict {
        set part_dict [dict create]
        foreach io_name [get_object_name $io_coll] {
            set gname "(none)"
            dict for {gname_tmp pat} $GROUP_DICT {
                if {[regexp "$pat" $io_name]} {
                    set gname $gname_tmp
                    break
                }
            }
            dict lappend part_dict $gname $io_name
        }
        dict set IO_GROUP_DICT $part_name $part_dict
    }

    if {[info exists argsp(-print)]} {
        echo ""
        dict for {part_name part_dict} $IO_GROUP_DICT {
            echo "====== $part_name"
            echo [format "%-60s" "PinGroup"]
            echo [string repeat "=" [expr 60]]
            dict for {gname io_list} $part_dict {
                echo [format "%-60s" $gname]
            }
            echo "\n"
        }
    }
    return $IO_GROUP_DICT
}

define_proc_attributes explore_design_io -info "Explore design IO" \
    -define_args { \
        {-top         "Explore from top"                                 ""         boolean optional}
        {-part_filter "Custom filter to get the partition cell (regexp)" expression string  optional}
        {-waive       "Waive pin/port list"                              waive_list list    optional}
        {-group       "Group constraint (regexp)"                        group_dict list    optional}
        {-print       "Show the result"                                  ""         boolean optional}
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

### === Top

### === Partition

