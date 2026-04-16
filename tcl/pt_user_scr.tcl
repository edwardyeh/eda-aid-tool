set timing_report_unconstrained_paths true

### === Private Function

### user help  {{{
set USER_HELP [dict create]
puts "Information: Type 'user_help' to show user procedure list."

proc user_help {args} {
    global USER_HELP
    parse_proc_arguments -args $args argsp

    set group_num [dict size $USER_HELP]

    # --- Get maximum proc name legnth
    set proc_len 0
    foreach proc_list [dict values $USER_HELP]
        foreach {proc_name description} $proc_list {
            set new_len [string length $proc_name]
            set proc_len [expr {max($proc_len, $new_len)}]
        }
    }

    if {[info exists argsp(-interactive)]} {
        # --- Interactive mode
        _print_group_list

        set cmd ""
        while {$cmd ne "q"} {
            puts -nonewline "Select group ('q' to exit, 'l' to show list): "
            flush stdout
            gets stdin cmd

            if {$cmd eq "q"} {
                return
            } elseif {$cmd eq "l" || $cmd >= $group_num} {
                _print_group_list
            } else {
                _print_proc_help $cmd $proc_len
            }
        }
    } else {
        # --- Normal mode
        for {set i 0} {$i < $group_num} {incr i} {
            _print_proc_help $i $proc_len
        }
    }
}

define_proc_attributes user_help -info "Show the user procedure list" \
    -define_args { \
        {-interactive "Interactive mode" "" boolean optional}
    }

proc _print_group_list {} {
    global USER_HELP
    set gid_len [string length [dict size $USER_HELP]]
    set gid 0

    puts ""
    foreach group_name [dict keys $USER_HELP] {
        puts [format "=== (%${gid_len}d) %s" $gid $group_name]
        incr gid
    }
    puts ""
}

proc _print_proc_help {gid proc_col_len} {
    global USER_HELP
    set group_list [dict keys $USER_HELP]
    set group_name [lindex $group_list $gid]

    puts ""
    puts [format "=== (%d) %s\n" $gid $group_name]
    foreach {proc_name description} [dict get $USER_HELP $group_name] {
        puts [format "  %-${proc_col_len}s   %s" $proc_name $description]
    }

    if {$proc_name ne ""} {puts ""}
}
#}}}

### === Flow Control

### flow control  {{{
dict append USER_HELP "Flow Control" {
    ree         "(alias) remote_execute -v"
    cus         "(alias) current_scenario"
    chs         "(alias) change_selection"
    rpcol       "(alias) report_collection"
    ""          ""
    cus0        "Focus to the first scenario of current scenarios"
    chcs        "Change scenarios by the regular expression"
    printfor    "Print items in a collection or list by for-loop"
}

alias ree   remote_execute -v
alias cus   current_scenario
alias chs   change_selection
alias rpcol report_collection

proc cus0 {}        { cus [index_col [cus] 0] }
proc chcs { regex } { cus [filter -regexp [cus -a] "full_name=~$regex"] }

proc printfor { data_coll } {
    if {[as_col -c $data_coll]} {
        set data_coll [get_object_name $data_coll]
    }
    foreach data $data_coll {
        echo $data
    }
}
#}}}

### === Get Collection

### get collection  {{{
dict append USER_HELP "Get Collection" {
    find_cells        "Find cells by the filter expression"
    get_cells_ckp     "Get clock pins of the cell collection"
    get_regs          "Get registers of the specific clock"
    get_mems          "Get memory collection from the cell collection"
    get_design_mems   "Get memory collection of the specific design"
    get_pins_attr     "Get the attribute of pins"
    get_ports_attr    "Get the attribute of ports"
    get_cells_attr    "Get the attribute of cells"
    get_nets_attr     "Get the attribute of nets"
    get_clk_frequency "Get the frequency of clocks"
    get_clk_period    "Get the period of clocks"
    get_hier_thp      "Get through pins of the hierarchical cell"
}

proc find_cells { args } {
    parse_proc_arguments -args $args argsp

    if {[info exists argsp(-regexp)]} {
        return [get_cells .* -hier -filter "full_name=~${argsp(expression)}" -regexp]
    } else {
        return [get_cells * -hier -filter "full_name=~${argsp(expression)}"]
    }
}

define_proc_attributes find_cells -info "Find cells by the filter expression" \
    -define_args { \
        { expression "Filter expression"       expression string  required}
        {-regexp     "Regular expression mode" ""         boolean optional}
    }

proc get_cells_ckp { cells } {
    return [get_pins -of [get_cells $cells] -filter "is_clock_pin"]
}

proc get_regs { args } {
    parse_proc_arguments -args $args argsp

    set reg_coll [all_register -clock [get_clocks $argsp(-clock)]]

    if {[info exists argsp(-exclude_icg)]} {
        set reg_coll [filter_col $reg_coll "is_integrated_clock_gating_cell==false"]
    }

    if {[info exists argsp(-only_icg)]} {
        set reg_coll [filter_col $reg_coll "is_integrated_clock_gating_cell==true"]
    }

    if {[info exists argsp(cell_coll)]} {
        set reg_coll [remove_from_col -inter $reg_coll [get_cells $argsp(cell_coll)]]
    }

    if {[info exists argsp(-filter)]} {
        if {[info exists argsp(-regexp)]} {
            set reg_coll [filter_col $reg_coll $argsp(-filter) -regexp]
        } else {
            set reg_coll [filter_col $reg_coll $argsp(-filter)]
        }
    }

    if {[info exists argsp(-clock_pin)]} {
        return [get_pins -quiet -of $reg_coll -filter "is_clock_pin==true"]
    } else {
        return $reg_coll
    }
}
            
define_proc_attributes get_regs -info "Get registers of the specific clock" \
    -define_args { \
        {-clock       "Clock collection"        collection string  required}
        {-filter      "Filter expression"       expression string  optional}
        {-regexp      "Regular expression mode" ""         boolean optional}
        {-exclude_icg "Exclude ICG cells"       ""         boolean optional}
        {-only_icg    "Only ICG cells"          ""         boolean optional}
        {-clock_pin   "Export clock pin"        ""         boolean optional}
        { cell_coll   "Cell collection"         collection string  optional}
    }

proc get_mems { cell_coll } {
    return [filter [get_cells $cell_coll] "is_black_box && is_memory_cell"]
}

proc get_design_mems { args } {
    parse_proc_arguments -args $args argsp

    set all_mem_coll {}
    foreach_in_col design [get_cells $design] {
        set name     [get_object_name $design]
        set mem_coll [get_cells * -hier -filter "full_name=~${name}/* && is_black_box && is_memory_cell"]   
        set mem_cnt  [sizeof_col $mem_coll]
        echo "\n=== $name ($mem_cnt)"
        if {[info exists argsp(-verbose)] && $mem_cnt > 0} {
            show_coll_attr $mem_coll ref_name
        }
        append_to_col all_mem_coll $mem_coll
    }
    echo ""

    if ![info exists argsp(-verbose)] { return $all_mem_coll }
}
            
define_proc_attributes get_design_mems -info "Get memory collection of the specific design" \
    -define_args { \
        { design  "Design collection" collection string  required}
        {-verbose "Print list"        ""         boolean optional}
    }

proc get_pins_attr  { coll attr } { return [get_attr [get_pins  $coll] $attr] }
proc get_ports_attr { coll attr } { return [get_attr [get_ports $coll] $attr] }
proc get_cells_attr { coll attr } { return [get_attr [get_cells $coll] $attr] }
proc get_nets_attr  { coll attr } { return [get_attr [get_nets  $coll] $attr] }

proc get_clk_frequency { clock_coll } {
    set clock_coll [get_clocks $clock_coll]
    set ckname_len [expr max([join [lmap s [get_object_name $clock_coll] {string length $s}] ","])]
    echo ""
    foreach_in_col clock $clock_coll {
        set clock_name [get_object_name $clock]
        set clock_freq [expr 1000.0 / [get_attr $clock period]]
        echo [format "%-${ckname_len}s : %9.4f Mhz" $clock_name $clock_freq]
    }
    echo ""
}

proc get_clk_period { clock_coll } {
    set clock_coll [get_clocks $clock_coll]
    set ckname_len [expr max([join [lmap s [get_object_name $clock_coll] {string length $s}] ","])]
    echo ""
    foreach_in_col clock $clock_coll {
        set clock_name [get_object_name $clock]
        echo [format "%-${ckname_len}s : %9.4f ns" $clock_name [get_attr $clock period]]
    }
    echo ""
}

proc get_hier_thp { args } {
    parse_proc_arguments -args $args argsp

    append_to_col thp_coll [get_pins  -quiet $argsp(-th)]
    append_to_col thp_coll [get_ports -quiet $argsp(-th)]

    set cmd     ""
    set cmd_opt ""

    if {[info exists argsp(-from)]} {
        set cmd "all_fanout -flat -trace all -quiet"
        append cmd_opt " -from ${argsp(-from)}"
    }

    if {[info exists argsp(-to)]} {
        set cmd "all_fanin -flat -trace all -quiet"
        append cmd_opt " -to ${argsp(-to)}"
    }

    set result_thp_coll ""
    foreach_in_col thp $thp_coll {
        set result [eval $cmd $cmd_opt -th \$thp]
        if {[sizeof_col $result] > 0} {
            append_to_col result_thp_coll $thp 
        }
    }

    return $result_thp_coll
}
            
define_proc_attributes get_hier_thp -info "Get through pins of the hierarchical cell" \
    -define_args { \
        {-from "From pins/ports"    collection string required}
        {-to   "To pins/ports"      collection string required}
        {-th   "Through pins/ports" collection string required}
    } \
    -define_arg_groups {
        {exclusive {-from -to}}
    }
#}}}

### === Report Timing

### report_timing (alias)  {{{
set ptcmd {}

set ptcmd_max "report_timing -delay max -trans -cap -derate -delta"
set ptcmd_min "report_timing -delay min -trans -cap -derate -delta"
set ptcmd [concat $ptcmd [list \
    rpmax   "$ptcmd_max" \
    rpmin   "$ptcmd_min" \
    rpmaxf  "$ptcmd_max -path full_clock" \
    rpminf  "$ptcmd_min -path full_clock" \
    rpmaxff "$ptcmd_max -path full_clock_ex" \
    rpminff "$ptcmd_min -path full_clock_ex" \
    rpmaxs  "report_timing -delay max -trans -cap -path short" \
    rpmins  "report_timing -delay min -trans -cap -path short" \
    ""      "" \
]]

set ptcmd_max "report_timing -delay max -trans -cap -derate -delta -pba ex"
set ptcmd_min "report_timing -delay min -trans -cap -derate -delta -pba ex"
set ptcmd [concat $ptcmd [list \
    rpmaxp   "$ptcmd_max" \
    rpminp   "$ptcmd_min" \
    rpmaxpf  "$ptcmd_max -path full_clock" \
    rpminpf  "$ptcmd_min -path full_clock" \
    rpmaxpff "$ptcmd_max -path full_clock_ex" \
    rpminpff "$ptcmd_min -path full_clock_ex" \
    rpmaxps  "report_timing -delay max -trans -cap -path short -pba ex" \
    rpminps  "report_timing -delay min -trans -cap -path short -pba ex" \
    ""       "" \
]]

set ptcmd_max "report_timing -delay max -trans -cap -derate -delta -pba ex -slack_less inf"
set ptcmd_min "report_timing -delay min -trans -cap -derate -delta -pba ex -slack_less inf"
set ptcmd [concat $ptcmd [list \
    rpmaxpi   "$ptcmd_max" \
    rpminpi   "$ptcmd_min" \
    rpmaxpif  "$ptcmd_max -path full_clock" \
    rpminpif  "$ptcmd_min -path full_clock" \
    rpmaxpiff "$ptcmd_max -path full_clock_ex" \
    rpminpiff "$ptcmd_min -path full_clock_ex" \
    rpmaxpis  "report_timing -delay max -trans -cap -path short -pba ex -slack_less inf" \
    rpminpis  "report_timing -delay min -trans -cap -path short -pba ex -slack_less inf" \
    ""        "" \
]]

set ptcmd_max "get_timing_path -delay max -path full_clock_ex"
set ptcmd_min "get_timing_path -delay min -path full_clock_ex"
set ptcmd [concat $ptcmd [list \
    gpmax   "$ptcmd_max" \
    gpmin   "$ptcmd_min" \
    gpmaxp  "$ptcmd_max -pba ex" \
    gpminp  "$ptcmd_min -pba ex" \
    gpmaxpi "$ptcmd_max -pba ex -slack_less inf" \
    gpminpi "$ptcmd_min -pba ex -slack_less inf" \
    ""      "" \
]]

set ptcmd [concat $ptcmd [list \
    rpcons  "report_constraint -all_vio -path end -ignore 0.0" \
    rpconsp "report_constraint -all_vio -path end -ignore 0.0 -pba ex" \
    ""      "" \
]]

set ptcmd_help {}
foreach {alias command} $ptcmd {
    if {$alias != ""} {
        alias $alias $command
        set new_cmd [list $alias "(alias) $command"]
    } else {
        set new_cmd {"" ""}
    }
    set ptcmd_help [concat $ptcmd_help $new_cmd]
}

foreach org_cmd {gpmax gpmaxp gpmaxpi gpmin gpminp gpminpi} {
    alias ${org_cmd}f  $org_cmd
    alias ${org_cmd}ff $org_cmd
}

dict append USER_HELP "Report Timing" $ptcmd_help
#}}}

### === Fanin/Fanout

### fanin/fanout (alias)  {{{
set ptcmd [list \
    afi   "all_fanin -flat" \
    afia  "all_fanin -flat -trace all" \
    afip  "all_fanin -flat -startpoints_only" \
    afipa "all_fanin -flat -startpoints_only -trace all" \
    ""    "" \
    afo   "all_fanout -flat" \
    afoa  "all_fanout -flat -trace all" \
    afop  "all_fanout -flat -endpoints_only" \
    afopa "all_fanout -flat -endpoints_only -trace all" \
    ""    "" \
]

set ptcmd_help {}
foreach {alias command} $ptcmd {
    if {$alias != ""} {
        alias $alias $command
        set new_cmd [list $alias "(alias) $command"]
    } else {
        set new_cmd {"" ""}
    }
    set ptcmd_help [concat $ptcmd_help $new_cmd]
}

dict append USER_HELP "Fanin/Fanout" $ptcmd_help
#}}}

### get memory fanin startpoint (get_mem_afip)  {{{
dict append USER_HELP "Fanin/Fanout" { get_mem_afip "Get memory fanin startpoint" }

proc get_mem_afip { mem_pin_coll } {
    set stp [afip -to $mem_pin_coll]
    return [remove_from_col $stp [filter $stp "object_class==port && ( \
                                                 full_name=~*_mbist_* \
                                                 || full_name=~*sram_rm* \
                                                 || full_name=~*sram_sd* \
                                               )"]]
}

define_proc_attributes get_mem_afip -info "Get memory fanin startpoint" \
    -define_args { \
        { mem_pin_coll "Memory pin collection" collection string required}
    }
#}}}

### get memory fanout endpoint (get_mem_afop)  {{{
dict append USER_HELP "Fanin/Fanout" { get_mem_afop "Get memory fanout endpoint" }

proc get_mem_afop { mem_pin_coll } {
    set edp [afop -from $mem_pin_coll]
    return [remove_from_col $edp [filter $edp "object_class==port && ( \
                                                 full_name=~*_mbist_* \
                                                 || full_name=~*sram_rm* \
                                                 || full_name=~*sram_sd* \
                                               )"]]
}

define_proc_attributes get_mem_afop -info "Get memory fanout endpoint" \
    -define_args { \
        { mem_pin_coll "Memory pin collection" collection string required}
    }
#}}}

### === Path/Instance Information

### show collection attribute (show_coll_attr)  {{{
dict append USER_HELP "Path/Instance Information" { show_coll_attr "Show collection attribute" }

proc show_coll_attr { args } {
    parse_proc_arguments -args $args argsp
    set header [list "Instance" "Attrubute ([join $argsp(attr_list) ","])"] 

    ## get attribute table
    set table {}
    foreach_in_col item $argsp(collection) {
        set attr_list ""
        foreach attr $argsp(attr_list) {
            set attr_value [get_attr -quiet $item $attr]
            if {[as_col -c $attr_value]} { 
                set attr_value [get_object_name $attr_value] 
            }

            if {$attr_value == ""} {
                lappend attr_list "NA"
            } else {
                lappend attr_list $attr_value
            }
        }
        lappend table [get_object_name $item]
        lappend table [join $attr_list ","]
    }

    ## get column length
    set inst_len 0
    set attr_len 0
    foreach {inst attr} [concat $header $table] {
        set new_len [string length $inst]
        if {$new_len > $inst_len} { set inst_len $new_len }
        set new_len [string length $attr]
        if {$new_len > $attr_len} { set attr_len $new_len }
    }
    set div [string repeat "=" [expr $inst_len + $attr_len + 6]]

    ## print table
    echo "\nCollection size: ([sizeof_col $argsp(collection)])\n"
    echo [format "%-${inst_len}s   %-s" [lindex $header 0] [lindex $header 1]]
    echo $div
    foreach {inst attr} $table {
        echo [format "%-${inst_len}s   %-s" $inst $attr]
    }
    echo ""
}

define_proc_attributes show_coll_attr -info "Show collection attribute" \
    -define_args { \
        { collection "Object collection"  collection string required}
        { attr_list  "List of attributes" list       string required}
    }
#}}}

### show object attribute (show_obj_attr)  {{{
dict append USER_HELP "Path/Instance Information" { show_obj_attr "Show object attribute" }

proc show_obj_attr { args } {
    parse_proc_arguments -args $args argsp

    if {[info exists argsp(-attribute)]} {
        set attr_regexp_list $argsp(-attribute)
    } else {
        set attr_regexp_list ".+"
    }

    foreach_in_col object $argsp(collection) {
        set attr_table ""
        set name_strlen 0
        set is_title "true"

        report_attr -app $object -format csv -out tmpfile
        
        set f [open "tmpfile" r]
        while {[gets $f line] >= 0} {
            if {$is_title} {
                set is_title "false"
                continue
            }

            set data_list [split $line ","]
            set attr_name [lindex $data_list 3] 

            foreach pattern $attr_regexp_list {
                if {[regexp $pattern $attr_name]} {
                    lappend attr_table $attr_name
                    lappend attr_table [lindex $data_list 2]
                    lappend attr_table [lindex $data_list 4]

                    set new_strlen  [string length $attr_name]
                    set name_strlen [expr {max($name_strlen, $new_strlen)}]
                    break
                }
            }
        }
        close $f
        file delete tmpfile

        set object_name [get_object_name $object]
        set object_type [get_attr $object object_class]

        puts ""
        puts "Object: $object_name (type: $object_type)"
        puts ""
        puts [format "%-${name_strlen}s    %-10s    %s" "Attrubute" "Type" "Value"]
        puts [string repeat "-" [expr {$name_strlen + 10 + 11 + 8}]]
        foreach {attr_name type value} $attr_table {
            echo [format "%-${name_strlen}s    %-10s    %s" $attr_name $type $value]
        }
        puts ""
    }
}

define_proc_attributes show_obj_attr -info "Show object attribute" \
    -define_args { \
        { collection "Object collection"           collection string required}
        {-attribute  "List of attributes (regexp)" attr_list  string optional}
    }
#}}}

### report timing path summary (rpsum)  {{{
dict append USER_HELP "Path/Instance Information" { rpsum "Report timing path summary" }

# Parameter Setting (RPSUM_CFG):
#   - debug          : <true|false>             (show debug information)
#   - dts_en         : <true|false>             (show delta sum)
#   - seg_en         : <true|false>             (enable path segment analysis)
#   - slk_on_rpt     : <true|false>             (show data latency/arrival/required/slack)
#   - ck_skew_on_rpt : <true|false>             (show clock latency)
#   - dplv_on_rpt    : <true|false>             (show path level)
#   - pc             : <tag> <regex_pattern>    (path classify by the regular expression)
#   - hcd            : <cell_type> {<from_pin> <to_pin> <comment> ...} 
#                                               (highlight cell delay)

proc rpsum { args } {
    global RPSUM_CFG
    parse_proc_arguments -args $args argsp
    set path_coll $argsp(path_coll)

    if {![as_col -c $path_coll] || ([get_attr $path_coll object_class] != "timing_path")} {
        echo "Error: required argument type 'timing_path'"
        return 0
    }

    global sh_host_mode
    if {($sh_host_mode == "manager") && ![sizeof_col [current_design]]} {
        echo "Error: need execute 'load_distributed_design' in thd DMSA mode"
        return 0
    }

    ## initial configuration
    if {![info exists RPSUM_CFG(debug)]            } { set RPSUM_CFG(debug)             "false"}
    if {![info exists RPSUM_CFG(dts_en)]           } { set RPSUM_CFG(dts_en)            "true" }
    if {![info exists RPSUM_CFG(seg_en)]           } { set RPSUM_CFG(seg_en)            "true" }
    if {![info exists RPSUM_CFG(slk_on_rpt)]       } { set RPSUM_CFG(slk_on_rpt)        "true" }
    if {![info exists RPSUM_CFG(ck_skew_on_rpt)]   } { set RPSUM_CFG(ck_skew_on_rpt)    "true" }
    if {![info exists RPSUM_CFG(dplv_on_rpt)]      } { set RPSUM_CFG(dplv_on_rpt)       "true" }
   #if {![info exists RPSUM_CFG(seg_clat_inc_crpr)]} { set RPSUM_CFG(seg_clat_inc_crpr) "true" }

    if {![info exists RPSUM_CFG(pc) ]} { set RPSUM_CFG(pc)  [dict create]}
    if {![info exists RPSUM_CFG(hcd)]} { set RPSUM_CFG(hcd) [dict create]}

    ## parsing information
    if {$RPSUM_CFG(debug)} { echo "## DEBUG: path information" }

    set PATH_INFO(stp) [get_attr $path_coll startpoint.full_name]
    set PATH_INFO(sck) [get_attr $path_coll startpoint_clock.full_name]
    set PATH_INFO(sed) [get_attr $path_coll startpoint_clock_open_edge_type]

    set PATH_INFO(edp) [get_attr $path_coll endpoint.full_name -q]
    set PATH_INFO(eck) [get_attr $path_coll endpoint_clock.full_name -q]
    set PATH_INFO(eed) [get_attr $path_coll endpoint_clock_open_edge_type -q]

    set PATH_INFO(grp) [get_attr $path_coll path_group.full_name -q]

    if {$PATH_INFO(grp) == ""} { set PATH_INFO(grp) "(none)" }

    set PATH_INFO(type) [get_attr $path_coll path_type]
    set PATH_INFO(scen) [get_attr $path_coll scenario_name -q]

    if {[get_attr $path_coll endpoint.object_class] == "port"} {
        set PATH_INFO(outp) "true"
    } else {
        set PATH_INFO(outp) "false"
    }

    if {$RPSUM_CFG(debug)} { echo "## DEBUG: clock latency" } 

    set PATH_INFO(sedv) [get_attr $path_coll startpoint_clock_open_edge_value -q]
    set PATH_INFO(eedv) [get_attr $path_coll endpoint_clock_open_edge_value -q]
    set PATH_INFO(llat) [get_attr $path_coll startpoint_clock_latency -q]
    set PATH_INFO(clat) [get_attr $path_coll endpoint_clock_latency -q]
    set PATH_INFO(crpr) [get_attr $path_coll common_path_pessimism -q]
    set PATH_INFO(lpg)  [get_attr $path_coll startpoint_clock_is_propagated]
    set PATH_INFO(cpg)  [get_attr $path_coll endpoint_clock_is_propagated -q]

    if {$PATH_INFO(sedv) == ""} { set PATH_INFO(sedv) 0       }
    if {$PATH_INFO(eedv) == ""} { set PATH_INFO(eedv) 0       }
    if {$PATH_INFO(llat) == ""} { set PATH_INFO(llat) 0       }
    if {$PATH_INFO(clat) == ""} { set PATH_INFO(clat) 0       }
    if {$PATH_INFO(crpr) == ""} { set PATH_INFO(crpr) 0       }
    if {$PATH_INFO(cpg)  == ""} { set PATH_INFO(cpg)  "false" }

    set PATH_INFO(skew) [expr $PATH_INFO(llat) - $PATH_INFO(clat) - $PATH_INFO(crpr)]

    if {$RPSUM_CFG(debug)} { echo "## DEBUG: data latency" }

    set PATH_INFO(edly) [get_attr $path_coll exception_delay]
    set PATH_INFO(idly) [get_attr $path_coll startpoint_input_delay_value -q]
    set PATH_INFO(odly) [get_attr $path_coll endpoint_output_delay_value -q]
    set PATH_INFO(unce) [get_attr $path_coll clock_uncertainty -q]
    set PATH_INFO(pmag) [get_attr $path_coll path_margin]
    set PATH_INFO(slk)  [get_attr $path_coll slack]

    if {$PATH_INFO(unce) == ""} {
        set PATH_INFO(unce) 0
    } elseif {$PATH_INFO(type) == "max"} {
        set PATH_INFO(unce) [expr -1 * $PATH_INFO(unce)]
    }

    if {$PATH_INFO(type) == "max"} {
        set PATH_INFO(lib) [get_attr $path_coll endpoint_setup_time_value -q]
    } else {
        set PATH_INFO(lib) [get_attr $path_coll endpoint_hold_time_value -q]
    }

    set PATH_INFO(arr) [expr [get_attr $path_coll arrival] + $PATH_INFO(sedv)]
    set PATH_INFO(req) [expr [get_attr $path_coll required] + $PATH_INFO(eedv)]

    set PATH_INFO(dlat) [expr $PATH_INFO(arr) - $PATH_INFO(llat) - $PATH_INFO(sedv)]
    if {$PATH_INFO(idly) != ""} {
        set PATH_INFO(dlat) [expr $PATH_INFO(dlat) - $PATH_INFO(idly)]
    }

    if {$RPSUM_CFG(debug)} { echo "## DEBUG: delta sum / path level / highlight cell delay" }

    set cmd_list {d ""}

    if {[get_attr $path_coll launch_clock_paths -q] == ""} {
        set lpath_existed "false"
    } else {
        set lpath_existed "true"
        set cmd_list [concat $cmd_list {l "launch_clock_paths."}]
    }

    if {[get_attr $path_coll capture_clock_paths -q] == ""} {
        set cpath_existed "false"
    } else {
        set cpath_existed "true"
        set cmd_list [concat $cmd_list {c "capture_clock_paths."}]
    }

    set full_clk [expr $lpath_existed && $cpath_existed]

    set PATH_INFO(full_clk) $full_clk
    set PATH_INFO(hcd)      {}
    set PATH_INFO(hcd_len)  0

    foreach {ptype attr} $cmd_list {
        set point_coll [get_attr $path_coll ${attr}points]
        set dt_var     "${ptype}dt"
        set lvl_var    "${ptype}lvl"

        lassign {0 0 "false" ""} pre_arr dt_sum hcd_det hcd_pi

        foreach_in_col point $point_coll {
            # delta sum
            set delta [get_attr $point annotated_delay_delta -q]
            if {$delta != ""} {
                set dt_sum [expr $dt_sum + $delta]
            }

            # highlight cell delay (datapath only)
            if {$attr == "" && ([get_attr $point object.object_class] != "port")} {
                set inst_name [get_attr $point object.full_name]
                set ref_name  [get_attr $point object.cell.ref_name]
                set arr       [get_attr $point arrival]
                set delay     [expr $arr - $pre_arr]
                set pre_arr   [get_attr $point arrival]

                if {[dict exists $RPSUM_CFG(hcd) $ref_name]} {
                    set pin_name [regsub {\S+\/} $inst_name {}]
                    set hcd_hit  "false"

                    foreach {pi po pcom} [dict get $RPSUM_CFG(hcd) $ref_name] {
                        if {$hcd_det} {
                            if {($hcd_pi == $pi) && ($pin_name == $po)} {
                                set hcd_det "false"
                                set PATH_INFO(hcd)     [concat $PATH_INFO(hcd) [list $pcom $delay]]
                                set new_hcd_len        [string length $pcom]
                                set PATH_INFO(hcd_len) [expr {max($PATH_INFO(hcd_len), $new_hcd_len)}]
                                break
                            }
                        } elseif {$pin_name == $pi} {
                            set hcd_hit "true"
                            set hcd_det "true"
                            set hcd_pi  $pi
                            break
                        }
                    }

                    if {$hcd_det && !$hcd_hit} {
                        set hcd_det "false"
                    }
                }
            }
        }
        set PATH_INFO($dt_var) $dt_sum

        # path level
        set cnt_dec 0
        set pin_cnt [llength [lsort -uni [get_attr $point_coll object.full_name]]]
        set fst_ckp [get_attr [index_col $point_coll 0] object]
        if {([get_attr $fst_ckp object_class] == "port") || \
            (($lvl_var != "dlvl") && ([get_attr $fst_ckp direction] == "out"))} {
            set cnt_dec 1
        }
        set PATH_INFO($lvl_var) [expr ($pin_cnt - $cnt_dec - 1) / 2]
    }

    # common clock path level
    set cc_inst ""
    if {$full_clk} {
        set cc_inst [get_attr $path_coll crpr_common_point.full_name -q]
        set cc_list {}
        if {$cc_inst != ""} {
            foreach inst_name [get_attr $point_coll object.full_name] {
                lappend cc_list $inst_name
                if {$inst_name == $cc_inst} { break }
            }
        }

        if {$PATH_INFO(req) == "INFINITY"} {
            set PATH_INFO(cclvl) 0
        } else {
            set PATH_INFO(cclvl) [expr ([llength [lsort -uni $cc_list]] - $cnt_dec) / 2]
        }
        set PATH_INFO(llvl) [expr $PATH_INFO(llvl) - $PATH_INFO(cclvl)]
        set PATH_INFO(clvl) [expr $PATH_INFO(clvl) - $PATH_INFO(cclvl)]
    }

    if {$RPSUM_CFG(seg_en) && [dict size $RPSUM_CFG(pc)]} {
        if {$RPSUM_CFG(debug)} { echo "## DEBUG: path segment" }

        foreach {ptype attr} $cmd_list {
            set lat_seg_var "${ptype}lat_seg"
            set dt_seg_var  "${ptype}dt_seg"
            set is_clk      [expr {$ptype == "l"} || {$ptype == "c"}]

            if {$RPSUM_CFG(debug)} { echo "## DEBUG: ptype: $ptype" }

            lassign {"" "" 0 0 0} pre_tag pre_inst pre_arr lat_sum dt_sum
            lassign {"false" 0} com_done com_lat

            foreach_in_col point [get_attr $path_coll ${attr}points] {
                set inst_name [get_attr $point object.full_name]
                set arr       [get_attr $point arrival]
                set delay     [expr $arr - $pre_arr]
                set pre_arr   [get_attr $point arrival]
                set delta     [get_attr $point annotated_delay_delta -q]
                if {$delta == ""} { set delta 0 }

                if {$inst_name == $pre_inst} { 
                    set pre_arr 0
                    continue 
                }
                set pre_inst $inst_name

                set is_hit "false"
                foreach {tag pattern} $RPSUM_CFG(pc) {
                    if {[regexp "^${pattern}\$" $inst_name]} { 
                        set is_hit "true"
                        break 
                    }
                }
                if {!$is_hit} { set tag "TP" }

                if {$RPSUM_CFG(debug)} {
                    echo [format "## DEBUG: (lat_sum/dt_sum/delay/delta): % 5.4f/% 5.4f/% 5.4f/% 5.4f" \
                        $lat_sum $dt_sum $delay $delta \
                    ]
                }

                if {!$com_done} { set com_lat [expr $com_lat + $delay] }

                if {$pre_tag == ""} {
                    set pre_tag $tag
                    set lat_sum $delay
                    set dt_sum  $delta
                } elseif {$is_clk && ($inst_name == $cc_inst)} {
                    if {$RPSUM_CFG(debug)} { echo "## DEBUG: check c" }
                    lappend $lat_seg_var [list "${tag}(c)" [expr $lat_sum + $delay]]
                    lappend $dt_seg_var  [list "${tag}(c)" [expr $dt_sum  + $delta]]
                    set pre_tag  ""
                    set com_done "true"
                } elseif {$tag != $pre_tag} {
                    if {$RPSUM_CFG(debug)} { echo "## DEBUG: check t ($pre_tag)" }
                    lappend $lat_seg_var [list $pre_tag $lat_sum]
                    lappend $dt_seg_var  [list $pre_tag $dt_sum ]
                    set pre_tag $tag
                    set lat_sum $delay
                    set dt_sum  $delta
                } else {
                    set lat_sum [expr $lat_sum + $delay]
                    set dt_sum  [expr $dt_sum  + $delta]
                }
            }

            # source latency & common clock path latency
            if {$is_clk} {
                set cpath  [index_col [get_attr $path_coll [string range $attr 0 end-1]] 0]
                set sc_lat [get_attr $cpath startpoint_clock_latency]
                set PATH_INFO(${ptype}lat_sc) $sc_lat

                if {$com_done} {
                    set PATH_INFO(${ptype}lat_com) [expr $sc_lat + $com_lat]
                } else {
                    set PATH_INFO(${ptype}lat_com) $sc_lat
                }

                if {$PATH_INFO(req) == "INFINITY"} {
                    set PATH_INFO(${ptype}lat_com) 0
                }
            }

            if {$lat_sum != 0} {
                lappend $lat_seg_var [list $pre_tag $lat_sum]
                lappend $dt_seg_var  [list $pre_tag $dt_sum ]
            }
            set PATH_INFO($lat_seg_var) [subst $$lat_seg_var]
            set PATH_INFO($dt_seg_var)  [subst $$dt_seg_var ]
        }
    }

    if {$PATH_INFO(req) == "INFINITY"} {
        set PATH_INFO(clat) "INFINITY"
    }

    ## report summary
    proc _report_func { path_info rpsum_cfg } {
        upvar 1 $path_info PATH_INFO
        upvar 1 $rpsum_cfg RPSUM_CFG
        set div1 " [string repeat "=" 60]"
        set div2 " [string repeat "-" 60]"
        set sc_type "($PATH_INFO(sed) $PATH_INFO(sck))"
        set ec_type "($PATH_INFO(eed) $PATH_INFO(eck))"

        set plen  [string length $PATH_INFO(stp)]
        set plen2 [string length $PATH_INFO(edp)]
        if {$plen2 > $plen} { set plen $plen2 }

        set strlen  [string length "$PATH_INFO(stp) $sc_type"]
        set strlen2 [string length "$PATH_INFO(edp) $ec_type"]
        if {$strlen2 > $strlen} { set strlen $strlen2 }

        echo ""
        # path information
        echo $div1
        if {$strlen > 80} {
            echo [format " Startpoint: %s" $PATH_INFO(stp)]
            echo [format "             %s" $sc_type]
            echo [format " Endpoint:   %s" $PATH_INFO(edp)]
            echo [format "             %s" $ec_type]
        } else {
            echo [format " Startpoint: %-${plen}s %s" $PATH_INFO(stp) $sc_type]
            echo [format " Endpoint:   %-${plen}s %s" $PATH_INFO(edp) $ec_type]
        }
        echo [format " Path group: %s" $PATH_INFO(grp)]
        echo [format " Delay type: %s" $PATH_INFO(type)]
        if {[llength $PATH_INFO(scen)]} {
            echo [format " Scenario:   %s" $PATH_INFO(scen)]
        }
        echo $div1

        # path latency
        if {$RPSUM_CFG(slk_on_rpt)} {
            echo [format " %-26s% 5.4f" "data latency:" $PATH_INFO(dlat)]
            echo [format " %-26s% 5.4f" "arrival:"      $PATH_INFO(arr)]
            echo [format " %-26s% 5.4f" "required:"     $PATH_INFO(req)]
            echo [format " %-26s% 5.4f" "slack:"        $PATH_INFO(slk)]
            set is_sub_div "false"

            if {$PATH_INFO(slk) != "INFINITY" && $PATH_INFO(cpg)} {
                if {!$is_sub_div} { set is_sub_div "true"; echo $div2 }
                echo [format " %-26s% 5.4f" "clock uncertainty:" $PATH_INFO(unce)]
            }
            if {!$PATH_INFO(outp) && $PATH_INFO(lib) != ""} {
                if {!$is_sub_div} { set is_sub_div "true"; echo $div2 }
                if {$PATH_INFO(type) == "max"} {
                    set lib_type "library setup:"
                } else {
                    set lib_type "library hold:"
                }
                echo [format " %-26s% 5.4f" $lib_type $PATH_INFO(lib)]
            }
            if {$PATH_INFO(idly) != ""} {
                if {!$is_sub_div} { set is_sub_div "true"; echo $div2 }
                echo [format " %-26s% 5.4f" "input delay:" $PATH_INFO(idly)]
            }
            if {$PATH_INFO(odly) != ""} {
                if {!$is_sub_div} { set is_sub_div "true"; echo $div2 }
                echo [format " %-26s% 5.4f" "output delay:" $PATH_INFO(odly)]
            }
            if {$PATH_INFO(pmag) != "UNINIT" && $PATH_INFO(pmag) != 0} {
                if {!$is_sub_div} { set is_sub_div "true"; echo $div2 }
                echo [format " %-26s% 5.4f" "path margin:" $PATH_INFO(pmag)]
            }

            if {[llength $PATH_INFO(hcd)]} {
                if {$PATH_INFO(hcd_len) > 25} {
                    set col_len [expr $PATH_INFO(hcd_len) + 1]
                } else {
                    set col_len 26
                }
                echo $div2
                foreach {pcom delay} $PATH_INFO(hcd) {
                    echo [format " %-${col_len}s% 5.4f" "${pcom}:" $delay]
                }
            }
            echo $div1
        }

        # clock latency
        if {$RPSUM_CFG(ck_skew_on_rpt)} {
            set is_div     "false"
            set is_sub_div "true"
            if {$PATH_INFO(edly) != "UNINIT"} {
                set is_sub_div "false"
                echo [format " %-26s% 5.4f" "max delay:" $PATH_INFO(edly)]
                set is_div "true"
            }
            if {$PATH_INFO(slk) != "INFINITY" && $PATH_INFO(edly) == "UNINIT"} {
                echo [format " %-26s% 5.4f" "launch clock edge value:"  $PATH_INFO(sedv)]
                echo [format " %-26s% 5.4f" "capture clock edge value:" $PATH_INFO(eedv)]
                set is_div "true"
            }
            if {$PATH_INFO(lpg)} {
                if {!$is_sub_div} { set is_sub_div "true"; echo $div2 }
                echo [format " %-26s% 5.4f" "launch clock latency:" $PATH_INFO(llat)]
                set is_div "true"
            }
            if {$PATH_INFO(cpg)} {
                if {!$is_sub_div} { set is_sub_div "true"; echo $div2 }
                echo [format " %-26s% 5.4f" "capture clock latency:" $PATH_INFO(clat)]
                set is_div "true"
            }
            if {$PATH_INFO(slk) != "INFINITY" && $PATH_INFO(lpg) && $PATH_INFO(cpg)} {
                if {!$is_sub_div} { set is_sub_div "true"; echo $div2 }
                echo [format " %-26s% 5.4f" "crpr:"                  $PATH_INFO(crpr)]
                echo [format " %-26s% 5.4f" "clock skew:"            $PATH_INFO(skew)]
                set is_div "true"
            }

            if {$is_div} {
                echo $div1
            }
        }

        # path delta / path level
        set is_div_end "false"

        if {$RPSUM_CFG(dts_en)} {
            set is_div_end "true"
            set dts_tag "D/"
            set dts_val [format "% 5.4f/" $PATH_INFO(ddt)]
            if {[info exists PATH_INFO(ldt)]} {
                append dts_tag "L/"
                append dts_val [format "%5.4f/" $PATH_INFO(ldt)]
            }
            if {[info exists PATH_INFO(cdt)] && $PATH_INFO(req) != "INFINITY"} {
                append dts_tag "C/"
                append dts_val [format "%5.4f/" $PATH_INFO(cdt)]
            }
            set dts_tag [string range $dts_tag 0 end-1]
            set dts_val [string range $dts_val 0 end-1]
            echo [format " %-26s%s" "delta sum  ($dts_tag):" $dts_val]
        }

        if {$RPSUM_CFG(dplv_on_rpt)} {
            set is_div_end "true"
            set dlvl_tag "D/"
            set dlvl_val [format "% d/" $PATH_INFO(dlvl)]
            if {[info exists PATH_INFO(cclvl)] && $PATH_INFO(req) != "INFINITY"} {
                append dlvl_tag "CP/"
                append dlvl_val [format "%d/" $PATH_INFO(cclvl)]
            }
            if {[info exists PATH_INFO(llvl)]} {
                append dlvl_tag "L/"
                append dlvl_val [format "%d/" $PATH_INFO(llvl)]
            }
            if {[info exists PATH_INFO(clvl)] && $PATH_INFO(req) != "INFINITY"} {
                append dlvl_tag "C/"
                append dlvl_val [format "%d/" $PATH_INFO(clvl)]
            }
            set dlvl_tag [string range $dlvl_tag 0 end-1]
            set dlvl_val [string range $dlvl_val 0 end-1]
            echo [format " %-26s%s" "path level ($dlvl_tag):" $dlvl_val]
        }

        if {$is_div_end} { echo $div1 }

        # path segment
        if {$RPSUM_CFG(seg_en) && ([dict size $RPSUM_CFG(pc)] == 0)} {
            echo " Segment: path classify patterns is unexisted."
            echo $div1
        } elseif {$RPSUM_CFG(seg_en)} {
            if {$PATH_INFO(full_clk)} {
                echo " Segment:  (report path type: full_clock_expanded)"
            } else {
                echo " Segment:  (report path type: full)"
            }
            echo $div2

            set str ""
            foreach item $PATH_INFO(dlat_seg) {
                lassign $item tag value
                set str [format "%s%s:% 5.4f " $str $tag $value]
            }
            echo [format " %-14s%s" "data latency:" $str]

            set str ""
            foreach item $PATH_INFO(ddt_seg) {
                lassign $item tag value
                set str [format "%s%s:% 5.4f " $str $tag $value]
            }
            echo [format " %-14s%s" "data delta:" $str]

            if {$PATH_INFO(full_clk)} {
                echo $div2
                set str ""
                foreach item $PATH_INFO(llat_seg) {
                    lassign $item tag value
                    set str [format "%s%s:% 5.4f " $str $tag $value]
                }
                echo [format " %-21s%s (SC:% 5.4f COM:% 5.4f)" "launch clk latency:" \
                    $str $PATH_INFO(llat_sc) $PATH_INFO(llat_com) \
                ]

                set str ""
                foreach item $PATH_INFO(ldt_seg) {
                    lassign $item tag value
                    set str [format "%s%s:% 5.4f " $str $tag $value]
                }
                echo [format " %-21s%s" "launch clk delta:" $str]

                if {$PATH_INFO(req) != "INFINITY"} {
                    echo $div2
                    set str ""
                    foreach item $PATH_INFO(clat_seg) {
                        lassign $item tag value
                        set str [format "%s%s:% 5.4f " $str $tag $value]
                    }
                    echo [format " %-21s%s (SC:% 5.4f COM:% 5.4f)" "capture clk latency:" \
                        $str $PATH_INFO(clat_sc) [expr $PATH_INFO(clat_com) + $PATH_INFO(crpr)] \
                    ]

                    set str ""
                    foreach item $PATH_INFO(cdt_seg) {
                        lassign $item tag value
                        set str [format "%s%s:% 5.4f " $str $tag $value]
                    }
                    echo [format " %-21s%s" "capture clk delta:" $str]
                }
            }
            echo $div1
        }
        echo ""
    }

    if {[info exists argsp(-out_summary)]} {
        redirect -tee $argsp(-out_summary) { _report_func PATH_INFO RPSUM_CFG }
    } elseif {[info exists argsp(-out_verbose)]} {
        redirect -tee $argsp(-out_verbose) { _report_func PATH_INFO RPSUM_CFG }
        echo "### Timing Report:\n" >> $argsp(-out_verbose)
        report_timing -trans -cap -derate -delta $path_coll >> $argsp(-out_verbose)
    } else {
        _report_func PATH_INFO RPSUM_CFG
    }
}

define_proc_attributes rpsum -info "Report timing path summary" \
    -define_args { \
        { path_coll   "Path collection"                        collection string required}
        {-out_summary "Dump summary to the file"               filepath   string optional}
        {-out_verbose "Dump summary & timing path to the file" filepath   string optional}
    }
#}}}

### report timing path information (rpinfo)  {{{
dict append USER_HELP "Path/Instance Information" { rpinfo "Report timing path information" }

proc rpinfo { args } {
    parse_proc_arguments -args $args argsp
    if {![info exists argsp(-clock)] && ![info exists argsp(-data)]} {
        return 0
    }

    global sh_host_mode
    if {($sh_host_mode == "manager") && ![sizeof_col [current_design]]} {
        echo "Error: need execute 'load_distributed_design' in thd DMSA mode"
        return 0
    }

    set info_type "latency"
    if {[info exists argsp(-type)]} { set info_type $argsp(-type) }

    lassign {"" "" "false" "false"} ptst pted nosi noaocv
    if {[info exists argsp(-from)  ]} { set ptst   $argsp(-from)   }
    if {[info exists argsp(-to)    ]} { set pted   $argsp(-to)     }
    if {[info exists argsp(-nosi)  ]} { set nosi   $argsp(-nosi)   }
    if {[info exists argsp(-noaocv)]} { set noaocv $argsp(-noaocv) }

    ## Get the point information of clock/data paths

    proc _get_point_list { info_type start_id path_coll } {
        set point_list {}
        foreach_in_col path $path_coll {
            foreach_in_col point [get_attr $path points] {
                set pt_name [get_attr $point object.full_name]
                set arr     [get_attr $point arrival]
                set delta   [get_attr $point annotated_delay_delta -q]
                set derate  [get_attr $point applied_derate -q]
                set tran    [get_attr $point transition -q]
                if {$info_type == "latency"} {
                    if {$delta  == ""} { set delta  0.0 }
                    if {$derate == ""} { set derate 1.0 }
                }
                lappend point_list [list $pt_name $arr $delta $derate $tran $start_id]
            }
            incr start_id
        }
        return $point_list
    }

    set cpath_list {}
    if {[info exists argsp(-clock)]} {
        set cpath_list [_get_point_list $info_type 0 $argsp(-clock)]
        set path       [index_col $argsp(-clock) 0]

        set clk_edge [get_attr $path startpoint_clock_open_edge_value -q]
        if {$clk_edge == ""} { set clk_edge 0.0 }
        set sclat [get_attr $path startpoint_clock_latency -q]
        if {$sclat == ""} { set sclat 0.0 }
    }

    set dpath_list {}
    if {[info exists argsp(-data)]} {
        set dpath_list [_get_point_list $info_type 0 $argsp(-data)]
    }

    ## Get the incremental list of clock/data paths

    proc _get_incr_list { path_type info_type nosi noaocv ptst pted point_list } {
        lassign [lrepeat 5 0] sum_lat last_arr last_id is_st is_ed

        set incr_list {}
        foreach point_info $point_list {
            lassign $point_info pt arr delta derate tran id

            set comm ""
            if {$id != $last_id} {
                if {$path_type == "clock"} {
                    set comm "(gclock)"
                } else {
                    set comm "(multi-data)"
                }
            }

            if {$info_type == "transition"} {
                set inc $tran
            } elseif {$info_type == "delta"} {
                set inc $delta
                if {$inc != ""} { set sum_lat [expr $sum_lat + $inc] }
            } else {
                if {$id != $last_id} {
                    set inc 0.0
                } else {
                    set inc [expr $arr - $last_arr]
                    if {$nosi  } { set inc [expr $inc - $delta ] }
                    if {$noaocv} { set inc [expr $inc / $derate] }
                }
                set sum_lat  [expr $sum_lat + $inc]
                set last_arr $arr
            }
            set last_id $id

            if {[sizeof_col [get_pins -quiet $pt]]} {
                set pt_name "$pt ([get_attr [get_cells -of [get_pins $pt]] ref_name])"
            } else {
                set pt_name "$pt (port)"
            }

            if {$pt == $ptst} {
                if {$info_type == "latency"} { 
                    set inc 0.0 
                }
                set is_st "true"
                set sum_lat $inc
                set incr_list [list [list $pt_name $inc $comm]]
            } else {
                lappend incr_list [list $pt_name $inc $comm]
            }

            if {$pt == $pted} {
                set is_ed "true"
                break
            }
        }
        return [list $incr_list $sum_lat $is_st $is_ed]
    }

    set cpath_ret [_get_incr_list "clock" $info_type $nosi $noaocv $ptst $pted $cpath_list]
    lassign $cpath_ret cpath_incr_list cpath_sum_lat is_st is_ed

    if {$is_ed} {
        set dpath_incr_list {}
        set dpath_sum_lat 0
    } else {
        set dpath_ret [_get_incr_list "data" $info_type $nosi $noaocv $ptst $pted $dpath_list]
        lassign $dpath_ret dpath_incr_list dpath_sum_lat is_st is_ed
        if {$is_st} {
            set cpath_incr_list {}
            set cpath_sum_lat 0
        }
    }
    set total_lat [expr $cpath_sum_lat + $dpath_sum_lat]

    ## Print result

    if {[info exists argsp(-verbose)]} {
        if {$info_type == "latency" && [info exists argsp(-clock)]} {
            echo ""
            echo "  === Clock edge value     : [format "% 8.4f" $clk_edge]"
            echo "  === Clock source latency : [format "% 8.4f" $sclat]"
        }

        set total_str [string totitle $info_type]
        if {[info exists argsp(-clock)] && [info exists argsp(-data)]} {
            set total_str "Clock+Data $total_str"
            if {[llength $dpath_incr_list]} {
                lset dpath_incr_list 0 2 "(data start)"
            }
        } elseif {[info exists argsp(-clock)]} {
            set total_str "Clock $total_str"
        } else {
            set total_str "Data $total_str"
        }

        if {[info exists argsp(-from)] || [info exists argsp(-to)]} {
            append total_str " (clip)"
        }

        set pt_col_len [string length $total_str]
        foreach pt_info [concat $cpath_incr_list $dpath_incr_list] {
            set new_len [string length [lindex $pt_info 0]]
            if {$new_len > $pt_col_len} { set pt_col_len $new_len }
        }
        set div [string repeat "=" [expr $pt_col_len + 2 + 8]]

        echo ""
        echo [format "  %-${pt_col_len}s  %8s" "Point" "Incr"]
        echo "  $div"
        if {[info exists argsp(-from)]} { 
            echo "  ..." 
        }

        foreach pt_info [concat $cpath_incr_list $dpath_incr_list] {
            lassign $pt_info pt_name inc comm
            set inc_str $inc
            if {$inc_str != ""} {
                set inc_str [format "% 8.4f" $inc]
            }
            echo [format "  %-${pt_col_len}s  %8s %s" $pt_name $inc_str $comm]
        }

        if {[info exists argsp(-to)]} { 
            echo "  ..." 
        }
        echo "  $div"
        if {$info_type != "transition"} {
            echo [format "  %-${pt_col_len}s  % 8.4f" $total_str $total_lat]
        }
        echo ""
    } elseif {[info exists argsp(-return_pin_list)]} {
        set pin_list {}
        foreach pt_info [concat $cpath_incr_list $dpath_incr_list] {
            lappend pin_list [lindex [lindex $pt_info 0] 0]
        }
        return $pin_list
    } else {
        return $total_lat
    }
}

define_proc_attributes rpinfo -info "Report timing path information" \
    -define_args { \
        {-clock           "Clock path collection"        collection string  optional}
        {-data            "Data path collection"         collection string  optional}
        {-from            "Specific startpoint"          pin        string  optional}
        {-to              "Specific endpoint"            pin        string  optional}
        {-nosi            "Remove SI effect"             ""         boolean optional}
        {-noaocv          "Remove AOCV effect"           ""         boolean optional}
        {-verbose         "Show all path info"           ""         boolean optional}
        {-return_pin_list "Return the pin list"          ""         boolean optional}
        {-type            "Info type (default: latency)" type       one_of_string \
            { optional value_help {values {"latency" "transition" "delta"}} }}
    } \
    -define_arg_groups {
        {exclusive {-verbose -return_pin_list}}
    }
#}}}

### get components of paths (gpcom)  {{{
dict append USER_HELP "Path/Instance Information" { gpcom "Get components of paths (suppert dump tcl/innvous script)" }

proc gpcom { args } {
    parse_proc_arguments -args $args argsp

    global sh_host_mode
    if {($sh_host_mode == "manager") && ![sizeof_col [current_design]]} {
        echo "Error: need execute 'load_distributed_design' in thd DMSA mode"
        return 0
    }

    array set coll_array {pin {} net {} cell {} stp {} edp {}}
    foreach_in_col path $argsp(path_coll) {
        set pin_coll [get_attr $path points.object]
        if {[info exists argsp(-pin) ]} { append_to_col -uni coll_array(pin)  $pin_coll                    }
        if {[info exists argsp(-net) ]} { append_to_col -uni coll_array(net)  [get_net -seg -of $pin_coll] }
        if {[info exists argsp(-cell)]} { append_to_col -uni coll_array(cell) [get_cells -of $pin_coll]    }
        if {[info exists argsp(-stp) ]} { append_to_col -uni coll_array(stp)  [index_col $pin_coll 0]      }
        if {[info exists argsp(-edp) ]} { append_to_col -uni coll_array(edp)  [index_col $pin_coll end]    }
    }

    if {[info exists argsp(-merge)]} {
        foreach type [array names coll_array] {
            append_to_col -uni coll_array(merge) $coll_array($type)
        }
    }

    foreach type [array names coll_array] {
        set ::user_${type}_coll $coll_array($type)
    }

    if {[info exists argsp(-out_coll)]} {
        redirect $argsp(-out_coll) {
            echo ""
            foreach type [array names coll_array] {
                switch $type {
                    "pin"   {set cmd {"get_pins  \[" "\]"}}
                    "net"   {set cmd {"get_nets  \[" "\]"}}
                    "cell"  {set cmd {"get_cells \[" "\]"}}
                    "stp"   {set cmd {"get_pins  \[" "\]"}}
                    "edp"   {set cmd {"get_pins  \[" "\]"}}
                    default {set cmd {"" ""}}
                }

                if {[sizeof_col $coll_array($type)] == 0} {
                    set cmd {"" ""}
                }

                echo "set user_${type}_coll \[[lindex $cmd 0]list \\"
                foreach_in_col inst $coll_array($type) {
                    echo "    [get_object_name $inst] \\"
                }
                echo "[lindex $cmd 1]\]\n"
            }
        }
    }

    if {[info exists argsp(-hl_inn)]} {
        redirect $argsp(-hl_inn) {
            echo "dehighlight"
            echo "\n### pins/ports"
            foreach_in_col inst $coll_array(pin) {
                if {[get_attr $inst object_class] == "port"} {
                    echo "highlight -color red \[get_ports [get_object_name $inst]\]"
                } else {
                    echo "highlight -color red \[get_pins [get_object_name $inst]\]"
                }
            }
            echo "\n### nets"
            foreach_in_col inst $coll_array(net) {
                echo "highlight -color red \[get_nets [get_object_name $inst]\]"
            }
            echo "\n### cells"
            foreach_in_col inst $coll_array(cell) {
                echo "highlight -color red \[get_cells [get_object_name $inst]\]"
            }
            echo ""
        }
    }
}

define_proc_attributes gpcom -info "Get components of paths" \
    -define_args { \
        { path_coll "Path collection"                             collection string  required}
        {-pin       "Get the pin collection of paths"             ""         boolean optional}
        {-net       "Get the net collection of paths"             ""         boolean optional}
        {-cell      "Get the cell collection of paths"            ""         boolean optional}
        {-stp       "Get the startpoint of paths"                 ""         boolean optional}
        {-edp       "Get the endpoint of paths"                   ""         boolean optional}
        {-merge     "Merge output collections"                    ""         boolean optional}
        {-out_coll  "Output collection to file"                   filepath   string  optional}
        {-hl_inn    "Create the highlight script for the Innvous" filepath   string  optional}
    }
#}}}

### write out path collection (write_path)  {{{
dict append USER_HELP "Path/Instance Information" { write_path "Write out path collection" }

proc write_path { args } {
    parse_proc_arguments -args $args argsp

    global sh_host_mode
    if {($sh_host_mode == "manager") && ![sizeof_col [current_design]]} {
        echo "Error: need execute 'load_distributed_design' in thd DMSA mode"
        return 0
    }

    if {![info exists argsp(-gpout)] && ![info exists argsp(-rpout)]} {
        echo "Information: no outfile option"
        return 0
    }

    if {[info exists argsp(-delay_type)] && ($argsp(-delay_type) == "min")} {
        set gpcmd "get_timing_path -delay min -pba ex -slack_less inf -path full_clock_ex"
        set rpcmd "report_timing   -delay min -pba ex -slack_less inf -path full_clock_ex \
                                   -tran -cap -derate -delta"
    } else {
        set gpcmd "get_timing_path -delay max -pba ex -slack_less inf -path full_clock_ex"
        set rpcmd "report_timing   -delay max -pba ex -slack_less inf -path full_clock_ex \
                                   -tran -cap -derate -delta"
    }

    if {[info exists argsp(-gpout)]} {
        redirect $argsp(-gpout) {
            echo ""
            echo "set user_cmd \"$gpcmd\""
            echo "set user_path_coll {}"
            echo ""

            foreach_in_col path $argsp(collection) {
                set pt_idx 0
                set max_pt [expr [sizeof_col [get_attr $path points]] - 1]
                echo "set user_path_coll \[add_to_col \$user_path_coll \[ \\"
                echo "  eval \$user_cmd \\"
                foreach_in_col point [get_attr $path points] {
                    if {$pt_idx == 0} {
                        if {[info exists argsp(-start_end_clk)]} {
                            echo "  -from [get_attr $path startpoint_clock.full_name] \\"
                            echo "  -th   [get_attr $point object.full_name] \\"
                        } else {
                            echo "  -from [get_attr $point object.full_name] \\"
                        }
                    } elseif {$pt_idx == $max_pt} {
                        if {[info exists argsp(-start_end_clk)]} {
                            echo "  -th   [get_attr $point object.full_name] \\"
                            echo "  -to   [get_attr $path endpoint_clock.full_name] \\"
                        } else {
                            echo "  -to   [get_attr $point object.full_name] \\"
                        }
                    } else {
                            echo "  -th   [get_attr $point object.full_name] \\"
                    }
                    incr pt_idx
                }
                echo "\]\]\n"
            }
        }
    }

    if {[info exists argsp(-rpout)]} {
        redirect $argsp(-rpout) {
            echo ""
            echo "set user_cmd \"$rpcmd\""
            echo ""

            foreach_in_col path $argsp(collection) {
                set pt_idx 0
                set max_pt [expr [sizeof_col [get_attr $path points]] - 1]
                echo "eval \$user_cmd \\"
                foreach_in_col point [get_attr $path points] {
                    if {$pt_idx == 0} {
                        if {[info exists argsp(-start_end_clk)]} {
                            echo "-from [get_attr $path startpoint_clock.full_name] \\"
                            echo "-th   [get_attr $point object.full_name] \\"
                        } else {
                            echo "-from [get_attr $point object.full_name] \\"
                        }
                    } elseif {$pt_idx == $max_pt} {
                        if {[info exists argsp(-start_end_clk)]} {
                            echo "-th   [get_attr $point object.full_name] \\"
                            echo "-to   [get_attr $path endpoint_clock.full_name] \\"
                        } else {
                            echo "-to   [get_attr $point object.full_name] \\"
                        }
                    } else {
                            echo "-th   [get_attr $point object.full_name] \\"
                    }
                    incr pt_idx
                }
            }
        }
    }
}

define_proc_attributes write_path -info "Write out path collection" \
    -define_args { \
        { collection    "Path collection"                           collection string        required}
        {-delay_type    "Type of path delay:"                       type       one_of_string \
            { optional value_help {values {"max" "min"}} }}
        {-start_end_clk "Path start from clock / end to clock"      ""         boolean       optional}
        {-gpout         "Output file path (base 'get_timing_path')" filepath   string        optional}
        {-rpout         "Output file path (base 'report_timing')"   filepath   string        optional}
    }
#}}}

### show instance information (show_inst_info_tsmc/show_inst_info_snps)  {{{
dict append USER_HELP "Path/Instance Information" { 
    show_inst_info_tsmc "Show instance information (tsmc)" 
    show_inst_info_snps "Show instance information (synopsys)" 
}

proc show_inst_info_tsmc { instances } {
    global sh_host_mode
    if {($sh_host_mode == "manager") && ![sizeof_col [current_design]]} {
        echo "Error: need execute 'load_distributed_design' in thd DMSA mode"
        return 0
    }

    set mb_types {2 "MB2*" 4 "MB4*" 8 "MB8*"}
    foreach inst [get_object_name [get_cells $instances]] {
        _get_inst_info $mb_types $inst
    }
}

define_proc_attributes show_inst_info_tsmc -info "Show instance information (tsmc)" \
    -define_args { \
        {instances "Instance list" collection string required}
    }

proc show_inst_info_snps { instances } {
    global sh_host_mode
    if {($sh_host_mode == "manager") && ![sizeof_col [current_design]]} {
        echo "Error: need execute 'load_distributed_design' in thd DMSA mode"
        return 0
    }

    set mb_types {2 "S??_FSD*M2*" 4 "S??_FSD*M4*" 8 "S??_FSD*M8*"}
    foreach inst [get_object_name [get_cells $instances]] {
        _get_inst_info $mb_types $inst
    }
}

define_proc_attributes show_inst_info_snps -info "Show instance information (synopsys)" \
    -define_args { \
        {instances "Instance list" collection string required}
    }

proc _sum_area { inst_coll } {
    set result 0
    foreach_in_col inst $inst_coll {
        set result [expr $result + [get_attr $inst area]]
    }
    return $result
}

proc _get_inst_info { mb_types_dict inst } {
#{{{
    if {$inst == [get_object_name [current_design]]} {
        set all_coll [get_cells * -hier -filter "is_hierarchical==false"]
    } else {
        set all_coll [get_cells * -hier -filter "is_hierarchical==false && full_name=~$inst/*"]
    }

    set reg_coll   [filter $all_coll "is_clock_network_cell==false && is_sequential==true"]
    set com_coll   [filter $all_coll "is_clock_network_cell==false && is_combinational==true"]
    set mem_coll   [filter $all_coll "is_black_box==true && is_memory_cell==true"]
    set ckreg_coll [filter $all_coll "is_clock_network_cell==true && is_sequential==true"]
    set ckcom_coll [filter $all_coll "is_clock_network_cell==true && is_combinational==true"]
    set reg_coll   [remove_from_col $reg_coll $mem_coll]

    set all_cnt   [sizeof_col $all_coll]
    set reg_cnt   [sizeof_col $reg_coll]
    set com_cnt   [sizeof_col $com_coll]
    set mem_cnt   [sizeof_col $mem_coll]
    set ckreg_cnt [sizeof_col $ckreg_coll]
    set ckcom_cnt [sizeof_col $ckcom_coll]
    set ck_cnt    [expr $ckreg_cnt + $ckcom_cnt]
    set other_cnt [expr $all_cnt - $reg_cnt - $com_cnt - $mem_cnt - $ck_cnt]

    set all_area   [_sum_area $all_coll]
    set reg_area   [_sum_area $reg_coll]
    set com_area   [_sum_area $com_coll]
    set mem_area   [_sum_area $mem_coll]
    set ckreg_area [_sum_area $ckreg_coll]
    set ckcom_area [_sum_area $ckcom_coll]
    set ck_area    [expr $ckreg_area + $ckcom_area]

    if {$other_cnt == 0} {
        set other_area 0
    } else {
        set other_area [expr $all_area - $com_area - $reg_area - $mem_area - $ck_area]
    }

    echo "" > mbff_list.tcl
    set reg1b_cnt $reg_cnt
    set total_bits 0
    set bit_cnt_dict [dict create]
    dict for {bit pattern} $mb_types_dict {
        set mb_list [filter $reg_coll "ref_name=~$pattern"]
        set bit_cnt [sizeof_col $mb_list]
        if {$bit_cnt > 0} {
            redirect -append mbff_list.tcl {
                echo "set mbff${bit}_list \[list \\"
                foreach_in_col reg $mb_list { echo "    [get_object_name $reg] \\" }
                echo "\]\n"
            }
        }
        set reg1b_cnt  [expr $reg1b_cnt - $bit_cnt]
        set total_bits [expr $total_bits + $bit_cnt * $bit]
        dict set bit_cnt_dict $bit $bit_cnt
    }
    set total_bits [expr $total_bits + $reg1b_cnt]
    set bit_cnt_dict [concat [list 1 $reg1b_cnt] $bit_cnt_dict]

    puts ""
    puts " ============================================================"
    puts " Instance: $inst"
    puts " ------------------------------------------------------------"
    puts " Total cell area  : [format "%.0f" $all_area]"
    puts " -- combinational : [format "%.0f" $com_area]"
    puts " -- sequential    : [format "%.0f" $reg_area]"
    puts " -- memory        : [format "%.0f" $mem_area]"
    puts " -- clock         : [format "%.0f" $ck_area]"
    puts " -- others        : [format "%.0f" $other_area]"
    puts " ------------------------------------------------------------"
    puts " Total cell count : $all_cnt"
    puts " -- combinational : $com_cnt"
    puts " -- sequential    : $reg_cnt"
    puts " -- memory        : $mem_cnt"
    puts " -- clock         : $ck_cnt"
    puts " -- others        : $other_cnt"
    puts " ------------------------------------------------------------"
    puts " Total clock cell : $ck_cnt"
    puts " -- combinational : $ckcom_cnt"
    puts " -- sequential    : $ckreg_cnt"
    puts " ------------------------------------------------------------"
    puts " Total reg bits   : $total_bits"
    dict for {bit cnt} $bit_cnt_dict {
        puts " -- ${bit}b reg count  : $cnt"
    }
    puts " ============================================================"
    puts ""
#}}}
}
#}}}

### show cells area / instance count (show_cells_area)  {{{
dict append USER_HELP "Path/Instance Information" { show_cells_area "Show cells area / instance count" }

proc show_cells_area { args } {
    parse_proc_arguments -args $args argsp
    set all_coll [get_cells -h]

    set cell_coll {}
    foreach_in_col cell [get_cells $argsp(cell_coll)] {
        if {[get_attr $cell is_hierarchical]} {
            append_to_col -uni cell_coll [filter $all_coll "full_name=~[get_object_name $cell]/* \
                                                            && is_hierarchical==false"]
        } else {
            append_to_col -uni cell_coll $cell
        }
    }

    set area 0
    foreach_in_col inst $cell_coll {
        set area [expr $area + [get_attr $inst area]]
    }
    echo [format "Area/Inst: %14.3f / %10d" $area [sizeof_col $cell_coll]]
}

define_proc_attributes show_cells_area -info "Show cells area / instance count" \
    -define_args { \
        { cell_coll "Cell collection" collection string required}
    }
#}}}

### estimate fix margin (estimate_fix_margin)  {{{
dict append USER_HELP "Path/Instance Information" { estimate_fix_margin "Estimate fix margin" }

proc estimate_fix_margin { args } {
    parse_proc_arguments -args $args argsp

    global sh_host_mode
    if {($sh_host_mode == "manager") && ![sizeof_col [current_design]]} {
        echo "Error: need execute 'load_distributed_design' in thd DMSA mode"
        return 0
    }

    set path [index_col $argsp(path) 0]
    set stp  [get_attr $path startpoint.full_name]
    set sck  [get_attr $path startpoint_clock.full_name]
    set sed  [get_attr $path startpoint_clock_open_edge_type]
    set edp  [get_attr $path endpoint.full_name]
    set eck  [get_attr $path endpoint_clock.full_name]
    set eed  [get_attr $path endpoint_clock_open_edge_type]
    set type [get_attr $path path_type]

    if {[info exists argsp(-pba)]} {
        set cmd_max "get_timing_path -delay max -path full_clock_ex -pba ex -slack_less inf"
        set cmd_min "get_timing_path -delay min -path full_clock_ex -pba ex -slack_less inf"
    } else {
        set cmd_max "get_timing_path -delay max -path full_clock_ex"
        set cmd_min "get_timing_path -delay min -path full_clock_ex"
    }

    lassign {0 0} pt_col_len pre_arr
    set point_list {}
    foreach_in_col point [get_attr $path points] {
        set pin_name [get_attr $point object.full_name]
        set ref_name [get_attr [get_cells -of [get_attr $point object]] ref_name]
        set pt_name  "$pin_name ($ref_name)"
        set arr      [get_attr $point arrival]
        set inc      [expr $arr - $pre_arr]
        set pre_arr  $arr

        set class  [get_attr $point object.object_class]
        set dir    [get_attr $point object.direction]
        set fanout ""
        if {$class == "pin" && $dir == "out"} {
            set fanout [get_attr [get_nets -of [get_attr $point object]] number_of_leaf_loads]
        }

        lassign {"--" "--"} max_margin min_margin
        if {$pin_name != $stp} {
            set max_margin [get_attr -quiet [eval $cmd_max -th $pin_name] slack]
            set min_margin [get_attr -quiet [eval $cmd_min -th $pin_name] slack]
        }
        lappend point_list [list $pt_name $fanout $inc $arr $max_margin $min_margin]

        if {[string length $pt_name] > $pt_col_len} {
            set pt_col_len [string length $pt_name]
        }
    }
    set total_arr $arr

    lassign {"--" "--"} lib_max lib_min
    set total_str "Arrival / Lib setup / Lib hold"
    if {[get_attr [index_col [get_attr $path points.object] end] object_class] != "port"} {
        set lib_max [get_attr -quiet [eval $cmd_max -to $edp] endpoint_setup_time_value]
        set lib_min [get_attr -quiet [eval $cmd_min -to $edp] endpoint_hold_time_value]
    }
    if {[string length $total_str] > $pt_col_len} {
        set pt_col_len [string length $total_str]
    }

    set div "  [string repeat "=" 60]"
    echo ""
    echo $div
    echo [format "  Startpoint: %s" $stp]
    echo [format "              %s" "($sed $sck)"]
    echo [format "  Endpoint:   %s" $edp]
    echo [format "              %s" "($eed $eck)"]
    echo [format "  Delay type: %s" $type]
    echo $div
    echo ""

    set div "  [string repeat "=" [expr $pt_col_len + 8 + 10 * 4]]"
    echo [format "  %-${pt_col_len}s  %6s  %8s  %8s  %8s  %8s"      ""       ""     ""        ""  "Setup"   "Hold"]
    echo [format "  %-${pt_col_len}s  %6s  %8s  %8s  %8s  %8s" "Point" "Fanout" "Incr" "Arrival" "Margin" "Margin"]
    echo $div
    foreach point_info $point_list {
        lassign $point_info pt_name fanout inc arr max_margin min_margin
        if {$fanout != ""} { set fanout [format "%6d" $fanout] }
        if {$max_margin != "--" && $max_margin != ""} { set max_margin [format "% 8.4f" $max_margin] }
        if {$min_margin != "--" && $min_margin != ""} { set min_margin [format "% 8.4f" $min_margin] }

        echo [format "  %-${pt_col_len}s  %6s  % 8.4f  % 8.4f  %8s  %8s" \
            $pt_name $fanout $inc $arr $max_margin $min_margin \
        ]
    }
    echo $div
    if {$lib_max != "--" && $lib_max != ""} { set lib_max [format "% 8.4f" $lib_max] }
    if {$lib_min != "--" && $lib_min != ""} { set lib_min [format "% 8.4f" $lib_min] }
    echo [format "  %-${pt_col_len}s  %6s  %8s  % 8.4f  %8s  %8s" \
        $total_str "" "" $arr $lib_max $lib_min \
    ]
    echo $div
    echo [format "  %-${pt_col_len}s  %6s  %8s  % 8.4f  %8s  %8s" \
        "Slack" "" "" [get_attr $path slack] "" "" \
    ]
    echo ""
}

define_proc_attributes estimate_fix_margin -info "Estimate fix margin" \
    -define_args { \
        { path "Path object" collection string  required}
        {-pba  "PBA mode"    ""         boolean optional}
    }
#}}}

### === Partition Timing Analysis

### io connect check (io_connect_check)  {{{
dict append USER_HELP "Partition Timing Analysis" { io_connect_check "Check I/O connect of the instance" }

proc io_connect_check { args } {
    parse_proc_arguments -args $args argsp

    global sh_host_mode
    if {[info exists sh_host_mode] && $sh_host_mode == "manager"} {
        echo "Error: not support DMSA mode"
        return 0
    }

    set report_type "slk"
    if {[info exists argsp(-type)]} {
        set report_type $argsp(-type)
    }

    set clock_coll [get_clocks -quiet]
    if {[info exists argsp(-clock)]} { 
        set clock_coll [get_clocks $argsp(-clock)] 
    }

    set cmd_opt ""
    if {[info exists argsp(-pba)]} {
        append cmd_opt " -pba ex -slack_less inf"
    }

    lassign {0 0} port_col_len pin_col_len
    set clk_col_len  {}
    set act_clk_coll {} 

    set pin_ignore_coll ""
    if {[info exists argsp(-pin_ignore)]} {
        set pin_ignore_coll [get_pins $argsp(-pin_ignore)]
    }

    set pad_ignore_coll ""
    if {[info exists argsp(-pad_ignore)]} {
        set pad_ignore_coll [get_ports $argsp(-pad_ignore)]
    }

    proc _path_trace {pin_dir instance} {
        upvar 1 clock_coll      clock_coll
        upvar 1 report_type     report_type
        upvar 1 cmd_opt         cmd_opt
        upvar 1 port_col_len    port_col_len
        upvar 1 pin_col_len     pin_col_len
        upvar 1 clk_col_len     clk_col_len
        upvar 1 act_clk_coll    act_clk_coll
        upvar 1 pin_ignore_coll pin_ignore_coll
        upvar 1 pad_ignore_coll pad_ignore_coll
        set result_list {}

        set inst_pi_coll [get_pins -of [index_col [get_cells $instance] 0] -filter "direction==$pin_dir"]
        set inst_pi_coll [remove_from_col $inst_pi_coll $pin_ignore_coll]

        foreach_in_col pin $inst_pi_coll {
            if {$pin_dir == "in"} {
                set port_coll [filter [afip -quiet -to   $pin] "object_class==port"]
            } else {
                set port_coll [filter [afop -quiet -from $pin] "object_class==port"]
            }
            set port_coll [remove_from_col $port_coll $pad_ignore_coll]

            set lclk_coll [remove_from_col -inter [get_attr -quiet $pin launch_clocks] $clock_coll]

            if {[sizeof_col $port_coll]} {
                set pin_col_len [expr max($pin_col_len, [string length [get_object_name $pin]])]

                foreach_in_col port $port_coll {
                    set port_col_len [expr max($port_col_len, [string length [get_object_name $port]])]

                    set path_coll {}
                    foreach_in_col clk $lclk_coll {
                        if {$pin_dir == "in"} {
                            set path [eval gpmax $cmd_opt -from $clk -th $port -th $pin]
                        } else {
                            set path [eval gpmax $cmd_opt -from $clk -th $pin -to $port]
                        }
                        if {[sizeof_col $path] > 0 && [get_attr $path slack] != "INFINITY"} {
                            append_to_col path_coll $path
                        }
                    }

                    if {[sizeof_col $path_coll]} {
                        set new_sz [sizeof_col $path_coll]
                        set old_sz [llength $clk_col_len]
                        if {$new_sz > $old_sz} {
                            set new_list    [lrepeat [expr $new_sz - $old_sz] 0]
                            set clk_col_len [concat $clk_col_len $new_list]
                        }

                        lassign {0 {}} pidx value_list
                        foreach_in_col path $path_coll {
                            append_to_col -uni act_clk_coll [get_attr $path startpoint_clock]
                            set clk_name [get_attr $path startpoint_clock.full_name]
                            set idly     [get_attr $path startpoint_input_delay_value -q]
                            if {$idly == ""} { set idly 0 }

                            if {$report_type == "slk"} {
                                set value [get_attr $path slack]
                            } elseif {$report_type == "dlat"} {
                                set arr   [get_attr $path arrival]
                                set llat  [get_attr $path startpoint_clock_latency]
                                set value [expr $arr - $llat - $idly]
                            } else {
                                set value [expr [get_attr $path arrival] - $idly]
                            }
                            lappend value_list [list $clk_name $value]

                            set new_len [string length $clk_name]
                            if {$new_len > [lindex $clk_col_len $pidx]} {
                                lset clk_col_len $pidx $new_len
                            }
                            incr pidx
                        }
                        lappend result_list [list [get_object_name $port] [get_object_name $pin] $value_list]
                    } else {
                        lappend result_list [list [get_object_name $port] [get_object_name $pin] "NA"]
                    }
                }
            }
        }
        return $result_list
    }

    ## port to instance trace
    set fanin_list [_path_trace "in" $argsp(instance)]

    ## instance to port trace
    set fanout_list [_path_trace "out" $argsp(instance)]

    ## print result
    echo "\n=== Clock Period:\n"
    set print_str ""
    foreach_in_col clk $act_clk_coll {
        append print_str [format "%s: %.4f, " [get_object_name $clk] [get_attr $clk period]]
    }
    echo [string range $print_str 0 end-2]

    if {$report_type == "slk"} {
        set print_str "data slack"
    } elseif {$report_type == "dlat"} {
        set print_str "data latency"
    } else {
        set print_str "arrival time"
    }
    echo "\n=== IO Connect Check Result ($print_str):\n"

    proc _print_result {dir_tag result_list} {
        upvar 1 clk_col_len  clk_col_len
        upvar 1 port_col_len port_col_len
        upvar 1 pin_col_len  pin_col_len

        foreach path_info $result_list {
            if {[lindex $path_info 2] == "NA"} {
                set print_str "NA | "
            } else {
                lassign {0 ""} pidx print_str
                foreach value_info [lindex $path_info 2] {
                    lassign $value_info clk_name value
                    set col_len [lindex $clk_col_len $pidx]
                    append print_str [format "%-${col_len}s : % 8.4f | " $clk_name $value]
                    incr pidx
                }
            }
            echo [format "%${port_col_len}s $dir_tag %-${pin_col_len}s ( %s )" \
                [lindex $path_info 0] [lindex $path_info 1] [string range $print_str 0 end-3] \
            ]
        }
        echo ""
    }

    _print_result "==>" $fanin_list
    _print_result "<==" $fanout_list
}

define_proc_attributes io_connect_check -info "Check I/O connect of the instance" \
    -define_args { \
        { instance   "Instance path"                        instance    string  required}
        {-clock      "Indicate the clock list, default all" clock_list  string  optional}
        {-type       "Report type (slk: slack, dlat: data latency, arr: arrival time; default is 'slk')" \
                                                            report_type string  optional}
        {-pba        "PBA exhaustive mode"                  ""          boolean optional}
        {-pin_ignore "Ignore through pin list"              pin_list    string  optional}
        {-pad_ignore "Ignore PAD list"                      pad_list    string  optional}
    }
#}}}

### === Top Timing Analysis

### instance-to-instance intra clock skew (cross_inst_intra_clock_skew)  {{{
dict append USER_HELP "Top Timing Analysis" { \
    cross_inst_intra_clock_skew "Instance-to-Instance intra clock skew" }

proc cross_inst_intra_clock_skew { args } {
    parse_proc_arguments -args $args argsp
    set clk_pin_coll [all_reg -clock $argsp(-clock) -clock_pins]

    eval report_clock_timing -$argsp(-delay_type) -type skew -clock $argsp(-clock) \
                             -from [filter $clk_pin_coll "full_name=~${argsp(-from)}/*"] \
                             -to   [filter $clk_pin_coll "full_name=~${argsp(-to)}/*"] \
                             -nworst $argsp(-nworst)
}

define_proc_attributes cross_inst_intra_clock_skew -info "Instance-to-Instance intra clock skew" \
    -define_args { \
        {-clock      "Specific clock"        clock         string required}
        {-from       "From instance"         from_instance string required}
        {-to         "To instance"           to_instance   string required}
        {-delay_type "Delay type"            type          one_of_string \
            { optional value_help {values {"setup" "hold"}} {default "setup"} }}
        {-nworst     "List N worst entries"  worst_entries int    { optional {min_value 1} {default 1} }}
    }
#}}}

### instance-to-instance inter clock skew (cross_inst_inter_clock_skew)  {{{
dict append USER_HELP "Top Timing Analysis" { \
    cross_inst_inter_clock_skew "Instance-to-Instance inter clock skew" }

proc cross_inst_inter_clock_skew { args } {
    parse_proc_arguments -args $args argsp
    set from_ckp_coll [all_reg -clock $argsp(-clock_from) -clock_pins]
    set to_ckp_coll   [all_reg -clock $argsp(-clock_to)   -clock_pins]

    eval report_clock_timing -$argsp(-delay_type) -type skew \
                             -from_clock $argsp(-clock_from) \
                             -from       [filter $from_ckp_coll "full_name=~${argsp(-from)}/*"] \
                             -to_clock   $argsp(-clock_to) \
                             -to         [filter $to_ckp_coll "full_name=~${argsp(-to)}/*"] \
                             -nworst $argsp(-nworst)
}

define_proc_attributes cross_inst_inter_clock_skew -info "Instance-to-Instance inter clock skew" \
    -define_args { \
        {-clock_from "From clock"            from_clock    string required}
        {-clock_to   "To clock"              to_clock      string required}
        {-from       "From instance"         from_instance string required}
        {-to         "To instance"           to_instance   string required}
        {-delay_type "Delay type"            type          one_of_string \
            { optional value_help {values {"setup" "hold"}} {default "setup"} }}
        {-nworst     "List N worst entries"  worst_entries int    { optional {min_value 1} {default 1} }}
    }
#}}}

### to instance clock latency (to_inst_clock_latency)  {{{
dict append USER_HELP "Top Timing Analysis" { \
    to_inst_clock_latency "To instance clock latency" }

proc to_inst_clock_latency { args } {
    parse_proc_arguments -args $args argsp
    set clk_pin_coll [all_reg -clock $argsp(-clock) -clock_pins]

    eval report_clock_timing -$argsp(-delay_type) -type latency -clock $argsp(-clock) \
                             -to [filter $clk_pin_coll "full_name=~${argsp(-to)}/*"] \
                             -nworst $argsp(-nworst)
}

define_proc_attributes to_inst_clock_latency -info "To instance clock latency" \
    -define_args { \
        {-clock      "Specific clock"        clock         string required}
        {-to         "To instance"           to_instance   string required}
        {-delay_type "Delay type"            type          one_of_string \
            { optional value_help {values {"setup" "hold"}} {default "setup"} }}
        {-nworst     "List N worst entries"  worst_entries int    { optional {min_value 1} {default 1} }}
    }
#}}}

### === PrimeTime GUI

### general  {{{
dict append USER_HELP "PrimeTime GUI" {
    hicall  "(alias) gui_change_highlight -remove -all_colors"
    hicclr  "(alias) gui_change_highlight -remove -coll"
    ""      ""
}

alias hicall gui_change_highlight -remove -all_colors
alias hicclr gui_change_highlight -remove -coll
#}}}

### show highlight palette (show_highlight_palette)  {{{
dict append USER_HELP "PrimeTime GUI" { show_highlight_palette "Show highlight palette" }

proc show_highlight_palette {} {
    echo ""
    echo "=== Highlight Palette"
    echo "  yellow"
    echo "  orange"
    echo "  red"
    echo "  green"
    echo "  blue"
    echo "  purple"
    echo "  light_orange"
    echo "  light_red"
    echo "  light_green"
    echo "  light_blue"
    echo "  light_purple"
    echo ""
}
#}}}

### highlight path (highlight_path)  {{{
dict append USER_HELP "PrimeTime GUI" { highlight_path "Highlight path" }

proc highlight_path { args } {
    parse_proc_arguments -args $args argsp

    foreach_in_col path $argsp(path_coll) {
        set cell_coll [get_cells -of [filter [get_attr $path points.object] "object_class==pin"]]
        set stp_coll  [get_attr $path startpoint]
        set edp_coll  [get_attr $path endpoint]

        if {[get_attr $stp_coll object_class] == "pin"} { set stp_coll [get_cells -of $stp_coll] }
        if {[get_attr $edp_coll object_class] == "pin"} { set edp_coll [get_cells -of $edp_coll] }

        gui_change_highlight -coll $path -remove
        if {$argsp(-netc) != "none"} {
            gui_change_highlight -coll $path -color $argsp(-netc)
        }

        if {[sizeof_col $cell_coll]} {
            gui_change_highlight -coll $cell_coll -remove
            if {$argsp(-cellc) != "none"} {
                gui_change_highlight -coll $cell_coll -color $argsp(-cellc)
            }
        }

        if {[sizeof_col $stp_coll]} {
            gui_change_highlight -coll $stp_coll -remove
            if {$argsp(-stpc) != "none"} {
                gui_change_highlight -coll $stp_coll -color $argsp(-stpc)
            }
        }

        if {[sizeof_col $edp_coll]} {
            gui_change_highlight -coll $edp_coll -remove
            if {$argsp(-edpc) != "none"} {
                gui_change_highlight -coll $edp_coll -color $argsp(-edpc)
            }
        }

        if {[info exists argsp(-spc_coll)]} {
            set spc_coll [remove_from_col -inter $cell_coll $argsp(-spc_coll)]
            if {[sizeof_col $spc_coll]} {
                gui_change_highlight -coll $spc_coll -remove
                if {$argsp(-spcc) != "none"} {
                    gui_change_highlight -coll $spc_coll -color $argsp(-spcc)
                }
                if {[info exists argsp(-print_spc)]} { printfor $spc_coll }
            }
        }
    }
}

define_proc_attributes highlight_path -info "Highlight path" \
    -define_args { \
        { path_coll "Path collection"                  collection string  required} 
        {-netc      "Highlight color of nets"          color      string  {optional {default "yellow"} }}
        {-cellc     "Highlight color of cells"         color      string  {optional {default "none"  } }}
        {-stpc      "Highlight color of startpoints"   color      string  {optional {default "none"  } }}
        {-edpc      "Highlight color of endpoints"     color      string  {optional {default "none"  } }}
        {-spc_coll  "Highlight special cells"          collection string  optional} 
        {-spcc      "Highlight color of special cells" color      string  {optional {default "red"   } }}
        {-print_spc "Print special cells in paths"     ""         boolean optional}
    }
#}}}

### highlight trace base on 'all_fanin' (highlight_trace)  {{{
dict append USER_HELP "PrimeTime GUI" { highlight_trace "Highlight trace base on 'all_fanin'" }

proc highlight_trace { args } {
    parse_proc_arguments -args $args argsp

    set cmd_opt ""
    if {[info exists argsp(-th)]} { append cmd_opt " -th {[get_object_name [get_pins $argsp(-th)]]}" }

    set pin_coll [eval all_fanin -flat -trace $argsp(-trace) -from $argsp(-from) -to $argsp(-to) $cmd_opt]
    append_to_col -uni cell_coll [get_cells -of $pin_coll -filter "is_hierarchical==false"]

    append_to_col -uni net_coll [get_nets -quiet -seg -of [filter $pin_coll "object_class==port && direction==out"]]
    append_to_col -uni net_coll [get_nets -quiet -seg -of [filter $pin_coll "object_class==pin  && direction==in "]]

    set stp_port_coll [get_ports -quiet $argsp(-from)]
    if {[sizeof_col $stp_port_coll]} {
        set stp_port_coll [filter $stp_port_coll "direction!=inout"]
    }

    set stp_cell_coll [get_cells -quiet -of [get_pins -quiet $argsp(-from)]]
    if {[sizeof_col $stp_cell_coll]} {
        set stp_cell_coll [filter $stp_cell_coll "is_hierarchical==false"]
    }

    set stp_coll [add_to_col -uni $stp_port_coll $stp_cell_coll]

    set edp_port_coll [get_ports -quiet $argsp(-to)]
    if {[sizeof_col $edp_port_coll]} {
        set edp_port_coll [filter $edp_port_coll "direction!=inout"]
    }

    set edp_cell_coll [get_cells -quiet -of [get_pins -quiet $argsp(-to)]]
    if {[sizeof_col $edp_cell_coll]} {
        set edp_cell_coll [filter $edp_cell_coll "is_hierarchical==false"]
    }

    set edp_coll [add_to_col $edp_port_coll $edp_cell_coll]

    append_to_col -uni cell_coll [add_to_col $stp_coll $edp_coll]

    if {[sizeof_col $net_coll]} {
        gui_change_highlight -coll $net_coll -remove
        if {$argsp(-netc) != "none"} {
            gui_change_highlight -coll $net_coll -color $argsp(-netc)
        }
    }

    if {[sizeof_col $cell_coll]} {
        gui_change_highlight -coll $cell_coll -remove
        if {$argsp(-cellc) != "none"} {
            gui_change_highlight -coll $cell_coll -color $argsp(-cellc)
        }
    }

    if {[sizeof_col $stp_coll]} {
        gui_change_highlight -coll $stp_coll -remove
        if {$argsp(-stpc) != "none"} {
            gui_change_highlight -coll $stp_coll -color $argsp(-stpc)
        }
    }

    if {[sizeof_col $edp_coll]} {
        gui_change_highlight -coll $edp_coll -remove
        if {$argsp(-edpc) != "none"} {
            gui_change_highlight -coll $edp_coll -color $argsp(-edpc)
        }
    }

    if {[info exists argsp(-spc_coll)]} {
        set spc_coll [remove_from_col -inter $cell_coll $argsp(-spc_coll)]
        if {[sizeof_col $spc_coll]} {
            gui_change_highlight -coll $spc_coll -remove
            if {$argsp(-spcc) != "none"} {
                gui_change_highlight -coll $spc_coll -color $argsp(-spcc)
            }
            if {[info exists argsp(-print_spc)]} { printfor $spc_coll }
        }
    }
}

define_proc_attributes highlight_trace -info "Highlight trace base on 'all_fanin'" \
    -define_args { \
        {-from      "From pins, ports"                 from_list    string  required} 
        {-to        "To pins, ports"                   to_list      string  required} 
        {-th        "Through pins"                     through_list string  optional} 
        {-netc      "Highlight color of nets"          color        string  {optional {default "yellow"} }}
        {-cellc     "Highlight color of cells"         color        string  {optional {default "yellow"} }}
        {-stpc      "Highlight color of startpoints"   color        string  {optional {default "none"  } }}
        {-edpc      "Highlight color of endpoints"     color        string  {optional {default "none"  } }}
        {-spc_coll  "Highlight special cells"          collection   string  optional} 
        {-spcc      "Highlight color of special cells" color        string  {optional {default "red"   } }}
        {-print_spc "Print special cells in paths"     ""           boolean optional}
        {-trace     "Type of network arcs to trace"    arc_types    one_of_string \
            { optional {default "timing"} value_help {values {"timing" "enabled" "all"}} }}
    }
#}}}

### select trace base on 'all_fanin' (select_trace)  {{{
dict append USER_HELP "PrimeTime GUI" { select_trace "Select trace base on 'all_fanin'" }

proc select_trace { args } {
    parse_proc_arguments -args $args argsp

    set cmd_opt ""
    if {[info exists argsp(-th)]} { append cmd_opt " -th {[get_object_name [get_pins $argsp(-th)]]}" }

    set pin_coll [eval all_fanin -flat -trace $argsp(-trace) -from $argsp(-from) -to $argsp(-to) $cmd_opt]
    append_to_col -uni cell_coll [get_cells -of $pin_coll -filter "is_hierarchical==false"]

    append_to_col -uni net_coll [get_nets -quiet -seg -of [filter $pin_coll "object_class==port && direction==out"]]
    append_to_col -uni net_coll [get_nets -quiet -seg -of [filter $pin_coll "object_class==pin  && direction==in "]]

    set stp_port_coll [get_ports -quiet $argsp(-from)]
    if {[sizeof_col $stp_port_coll]} {
        set stp_port_coll [filter $stp_port_coll "direction!=inout"]
    }

    set stp_cell_coll [get_cells -quiet -of [get_pins -quiet $argsp(-from)]]
    if {[sizeof_col $stp_cell_coll]} {
        set stp_cell_coll [filter $stp_cell_coll "is_hierarchical==false"]
    }

    set stp_coll [add_to_col -uni $stp_port_coll $stp_cell_coll]

    set edp_port_coll [get_ports -quiet $argsp(-to)]
    if {[sizeof_col $edp_port_coll]} {
        set edp_port_coll [filter $edp_port_coll "direction!=inout"]
    }

    set edp_cell_coll [get_cells -quiet -of [get_pins -quiet $argsp(-to)]]
    if {[sizeof_col $edp_cell_coll]} {
        set edp_cell_coll [filter $edp_cell_coll "is_hierarchical==false"]
    }

    set edp_coll [add_to_col $edp_port_coll $edp_cell_coll]

    append_to_col -uni cell_coll [add_to_col $stp_coll $edp_coll]

    if {[info exists argsp(-spc_coll)]} {
        set spc_coll [remove_from_col -inter $cell_coll $argsp(-spc_coll)]
        if {[sizeof_col $spc_coll]} {
            if {[info exists argsp(-print_spc)]} { printfor $spc_coll }
        }
        set high_coll $spc_coll 
    } else {
        set high_coll [add_to_col $cell_coll $net_coll]
    }

    change_selection $high_coll
}

define_proc_attributes select_trace -info "Select trace base on 'all_fanin'" \
    -define_args { \
        {-from      "From pins, ports"                   from_list    string  required} 
        {-to        "To pins, ports"                     to_list      string  required} 
        {-th        "Through pins"                       through_list string  optional} 
        {-spc_coll  "Only select special cells in route" collection   string  optional} 
        {-print_spc "Print special cells in paths"       ""           boolean optional}
        {-trace     "Type of network arcs to trace"      arc_types    one_of_string \
            { optional {default "timing"} value_help {values {"timing" "enabled" "all"}} }}
    }
#}}}

### select cell in the path (select_in_path)  {{{
dict append USER_HELP "PrimeTime GUI" { select_in_path "Select cell in the path" }

proc select_in_path { args } {
    parse_proc_arguments -args $args argsp
    set cell_coll [get_cells -of [get_attr $path_coll points.object]]

    if {[info exists argsp(-spc_coll)]} {
        set spc_coll [remove_from_col -inter $cell_coll $argsp(-spc_coll)]
        if {[sizeof_col $spc_coll]} {
            if {[info exists argsp(-print_spc)]} { printfor $spc_coll }
            change_selection $spc_coll
        }
    }
}

define_proc_attributes select_in_path -info "Select cell in the path" \
    -define_args { \
        {-path_coll "Path collection"                    collection string  required}
        {-spc_coll  "Only select special cells in route" collection string  required} 
        {-print_spc "Print special cells in paths"       ""         boolean optional}
    }
#}}}

