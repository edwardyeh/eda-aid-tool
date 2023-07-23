set timing_report_unconstrained_paths true

### general     {{{
alias ree   remote_execute
alias cus   current_scenario
alias chs   change_selection
#}}}

### report_timing (setup)   {{{
alias rpmax             report_timing -delay_type max -cap -tran -derate -delta
alias rpmaxpba          rpmax    -pba_mode ex
alias rpmaxinf          rpmax    -slack_lesser_than inf
alias rpmaxpbainf       rpmaxpba -slack_lesser_than inf

alias rpmaxfc           rpmax      -path_type full_clock
alias rpmaxpbafc        rpmaxpba   -path_type full_clock
alias rpmaxfcinf        rpmaxfc    -slack_lesser_than inf
alias rpmaxpbafcinf     rpmaxpbafc -slack_lesser_than inf

alias rpmaxfce          rpmax       -path_type full_clock_ex
alias rpmaxpbafce       rpmaxpba    -path_type full_clock_ex
alias rpmaxfceinf       rpmaxfce    -slack_lesser_than inf
alias rpmaxpbafceinf    rpmaxpbafce -slack_lesser_than inf

alias gpmax             get_timing_path -delay_type max
alias gpmaxpba          gpmax    -pba_mode ex
alias gpmaxfce          gpmax    -path_type full_clock_ex
alias gpmaxpbafce       gpmaxpba -path_type full_clock_ex
#}}}

### report_timing (hold)    {{{
alias rpmin             report_timing -delay_type min -cap -tran -derate -delta
alias rpminpba          rpmin    -pba_mode ex
alias rpmininf          rpmin    -slack_lesser_than inf
alias rpminpbainf       rpminpba -slack_lesser_than inf

alias rpminfc           rpmin      -path_type full_clock
alias rpminpbafc        rpminpba   -path_type full_clock
alias rpminfcinf        rpminfc    -slack_lesser_than inf
alias rpminpbafcinf     rpminpbafc -slack_lesser_than inf

alias rpminfce          rpmin       -path_type full_clock_ex
alias rpminpbafce       rpminpba    -path_type full_clock_ex
alias rpminfceinf       rpminfce    -slack_lesser_than inf
alias rpminpbafceinf    rpminpbafce -slack_lesser_than inf

alias gpmin             get_timing_path -delay_type min
alias gpminpba          gpmin    -pba_mode ex
alias gpminfce          gpmin    -path_type full_clock_ex
alias gpminpbafce       gpminpba -path_type full_clock_ex
#}}}

### all_fanin   {{{
alias afi       all_fanin -flat
alias afist     all_fanin -flat -startpoints_only
alias afia      afi   -trace all
alias afiast    afist -trace all

proc afi_core {cmd pins} {
    # args: -to pin0 [-from pin1] [-th pin2]
    if {[llength $pins] == 1} {
        set stp_coll [$cmd -to [lindex $pins 0]]
    } elseif {[llength $pins] == 2} {
        set stp_coll [$cmd -to [lindex $pins 0] -from [lindex $pins 1]]
    } elseif {[llength $pins] == 3} {
        set stp_coll [$cmd -to [lindex $pins 0] -from [lindex $pins 1] -th [lindex $pins 2]]
    }
    
    foreach_in_collection stp $stp_coll {
        echo [get_obj $stp]
    }
}

proc afi_list    {pins} { afi_core "afi"    $pins }
proc afist_list  {pins} { afi_core "afist"  $pins }
proc afia_list   {pins} { afi_core "afia"   $pins }
proc afiast_list {pins} { afi_core "afiast" $pins }
#}}}

### all_fanout  {{{
alias afo       all_fanout -flat
alias afoed     all_fanout -flat -endpoints_only
alias afoa      afo   -trace all
alias afoaed    afoed -trace all

proc afo_core {cmd pins} {
    # args: -from pin0 [-to pin1] [-th pin2]
    if {[llength $pins] == 1} {
        set stp_coll [$cmd -from [lindex $pins 0]]
    } elseif {[llength $pins] == 2} {
        set stp_coll [$cmd -from [lindex $pins 0] -to [lindex $pins 1]]
    } elseif {[llength $pins] == 3} {
        set stp_coll [$cmd -from [lindex $pins 0] -to [lindex $pins 1] -th [lindex $pins 2]]
    }
    
    foreach_in_collection stp $stp_coll {
        echo [get_obj $stp]
    }
}

proc afo_list    {pins} { afo_core "afo"    $pins }
proc afoed_list  {pins} { afo_core "afoed"  $pins }
proc afoa_list   {pins} { afo_core "afoa"   $pins }
proc afoaed_list {pins} { afo_core "afoaed" $pins }
#}}}

### timing path brief   {{{
proc rptbf_core {case cmd group parm} {
#{{{
    if {$case == 0} { 
        # args: [-group group] -to pin0 [-from pin1] [-th pin2]
        if {$group != ""} {
            set grp_opt "-group"
            set grp_arg "$group"
        } else {
            set grp_opt ""
            set grp_arg ""
        }

        if {[llength $parm] == 1} {
            set path_coll [$cmd $grp_opt $grp_arg -to [lindex $parm 0]]
        } elseif {[llength $parm] == 2} {
            set path_coll [$cmd $grp_opt $grp_arg -to [lindex $parm 0] -from [lindex $parm 1]]
        } elseif {[llength $parm] == 3} {
            set path_coll [$cmd $grp_opt $grp_arg -to [lindex $parm 0] -from [lindex $parm 1] \
                                                  -th [lindex $parm 2]]
        }
    } elseif {$case == 1} {
        set path_coll $parm
    }

    set stp  [get_obj [get_att $path_coll startpoint]]
    set sck  [get_obj [get_att $path_coll startpoint_clock]]
    set sed  [get_att $path_coll startpoint_clock_open_edge_type]
             
    set edp  [get_obj [get_att $path_coll endpoint]]
    set eck  [get_obj [get_att $path_coll endpoint_clock]]
    set eed  [get_att $path_coll endpoint_clock_open_edge_type]
             
    set grp  [get_obj [get_att $path_coll path_group]]
    set type [get_att $path_coll path_type]
    set epin [get_att $path_coll endpoint_clock_pin]

    set sev  [get_att $path_coll startpoint_clock_open_edge_value]
    set eev  [get_att $path_coll endpoint_clock_open_edge_value]
    set arr  [expr [get_att $path_coll arrival] + $sev]
    set req  [expr [get_att $path_coll required] + $eev]
    set slk  [get_att $path_coll slack]

    set slat [get_att $path_coll startpoint_clock_latency]
    set elat [get_att $path_coll endpoint_clock_latency]
    set crpr [get_att $path_coll common_path_pessimism]
    set skew [expr $slat - $elat - $crpr]

    if {$type == "max"} {
        set cor_cmd "-setup"
    } else {
        set cor_cmd "-hold"
    }

    puts ""
    if {$sck == $eck} {
        report_clock_timing $cor_cmd -type skew -from $stp -to $epin
    } else {
        report_clock_timing $cor_cmd -type interclock_skew -from_clock $sck -from $stp -to_clock $eck -to $epin
    }

    if {$case == 0 && [llength $parm] >= 2} {
        set sstp [lindex $parm 1]
    } else {
        set sstp $stp
    }

    set splen [string length $edp]
    if {[string length $sstp] > $splen} {
        set splen [string length $sstp]
    }

    if {$splen > 80} {
        set stp_des "Startpoint: $sstp\n            ($sed $sck)"
        set edp_des "Endpoint:   $edp\n            ($eed $eck)"
    } else {
        set stp_des "Startpoint: $sstp ($sed $sck)"
        set edp_des "Endpoint:   $edp ($eed $eck)"
    }

    puts ""
    puts ""
    puts "  ============================================================"
    puts "  $stp_des"
    puts "  $edp_des"
    if {$case == 0 && [llength $parm] == 3} {
    puts "  Throughput: [lindex $parm 2]"
    }
    puts "  path group: $grp"
    puts "  delay type: $type"
    puts "  ============================================================"
    puts "  data latency:              [format "%.4f" [expr $arr - $slat - $sev]]"
    puts "  arrival:                   [format "%.4f" $arr]"
    puts "  required:                  [format "%.4f" $req]"
    puts "  slack:                     [format "%.4f" $slk]"
    puts "  ============================================================"
    puts "  startpoint clk edge value: [format "%.4f" $sev]"
    puts "  endpoint clk edge value:   [format "%.4f" $eev]"
    puts "  launch clock latency:      [format "%.4f" $slat]"
    puts "  capture clock latency:     [format "%.4f" $elat]"
    puts "  crpr:                      [format "%.4f" $crpr]"
    puts "  clock skew:                [format "%.4f" $skew]"
    puts "  ============================================================"
    puts ""
    puts ""
#}}}
}

proc rpmaxpba_bf {pins} { rptbf_core 0 "gpmaxpba" "" $pins }
proc rpminpba_bf {pins} { rptbf_core 0 "gpminpba" "" $pins }

proc rpmaxpbag_bf {group pins} { rptbf_core 0 "gpmaxpba" $group $pins }
proc rpminpbag_bf {group pins} { rptbf_core 0 "gpminpba" $group $pins }

proc gpmaxpba_bf {coll} { rptbf_core 1 "" "" $coll }
proc gpminpba_bf {coll} { rptbf_core 1 "" "" $coll }
#}}}

### instance information {{{

proc sum_area {inst_coll} {
    set sum_area 0
    foreach_in_collection inst $inst_coll {
        set sum_area [expr $sum_area + [get_att $inst area]]
    }
    return $sum_area
}

proc get_inst_info_core {mb_list inst} {
#{{{
    set all_cell_coll [get_cells -hier -filter "full_name=~${inst}/* && is_hierarchical==false"]
    set reg_coll      [filter $all_cell_coll "is_sequential==true && is_clock_network_cell==false"]
    set com_coll      [filter $all_cell_coll "is_combinational==true && is_clock_network_cell==false"]
    set mem_coll      [filter $all_cell_coll "is_black_box==true && is_memory_cell==true"]
    set ckreg_coll    [filter $all_cell_coll "is_sequential==true && is_clock_network_cell==true"]
    set ckcom_coll    [filter $all_cell_coll "is_combinational==true && is_clock_network_cell==true"]
    set reg_coll      [remove_from_collection $reg_coll $mem_coll]

    set all_cell_cnt [sizeof_collection $all_cell_coll]
    set reg_cnt      [sizeof_collection $reg_coll]
    set com_cnt      [sizeof_collection $com_coll]
    set mem_cnt      [sizeof_collection $mem_coll]
    set ckreg_cnt    [sizeof_collection $ckreg_coll]
    set ckcom_cnt    [sizeof_collection $ckcom_coll]
    set ck_cnt       [expr $ckreg_cnt + $ckcom_cnt]
    set other_cnt    [expr $all_cell_cnt - $reg_cnt - $com_cnt - $mem_cnt - $ck_cnt]

    set all_area   [sum_area $all_cell_coll]
    set reg_area   [sum_area $reg_coll]
    set com_area   [sum_area $com_coll]
    set mem_area   [sum_area $mem_coll]
    set ckreg_area [sum_area $ckreg_coll]
    set ckcom_area [sum_area $ckcom_coll]
    set ck_area    [expr $ckreg_area + $ckcom_area]

    if {$other_cnt == 0} {
        set other_area 0
    } else {
        set other_area [expr $all_area - $com_area - $reg_area - $mem_area - $ck_area]
    }

    redirect reg2b.list {
        set reg2b_list [get_obj [filter $reg_coll "ref_name=~[lindex $mb_list 0]"]]
        foreach reg $reg2b_list {
            puts $reg
        }
    }
    redirect reg4b.list {
        set reg4b_list [get_obj [filter $reg_coll "ref_name=~[lindex $mb_list 1]"]]
        foreach reg $reg4b_list {
            puts $reg
        }
    }
    redirect reg8b.list {
        set reg8b_list [get_obj [filter $reg_coll "ref_name=~[lindex $mb_list 2]"]]
        foreach reg $reg8b_list {
            puts $reg
        }
    }

    set reg2b_cnt  [llength $reg2b_list]
    set reg4b_cnt  [llength $reg4b_list]
    set reg8b_cnt  [llength $reg8b_list]
    set reg1b_cnt  [expr $reg_cnt - $reg2b_cnt - $reg4b_cnt - $reg8b_cnt]
    set total_reg_bits [expr $reg1b_cnt + $reg2b_cnt * 2 + $reg4b_cnt * 4 + $reg8b_cnt * 8]

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
    puts " Total cell count : $all_cell_cnt"
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
    puts " Total reg bits   : $total_reg_bits"
    puts " -- 1b reg count  : $reg1b_cnt"
    puts " -- 2b reg count  : $reg2b_cnt"
    puts " -- 4b reg count  : $reg4b_cnt"
    puts " -- 8b reg count  : $reg8b_cnt"
    puts " ============================================================"
    puts ""
#}}}
}

proc get_inst_info_tsmc {inst_list} {
    set tsmc_mb_list "MB2* MB4* MB8*"
    foreach inst $inst_list {
        get_reg_bits_core $tsmc_mb_list $inst
    }
}

proc get_inst_info_virage {inst_list} {
    set virage_mb_list "none none none"
    foreach inst $inst_list {
        get_reg_bits_core $virage_mb_list $inst
    }
}
#}}}

