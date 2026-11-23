set here [file dirname [file normalize [info script]]]
source [file join $here ../../cadence genus_fdsc.tcl]
fdsc_read_libs ss_150C_1v60
read_hdl -language v2001 [file join $here smoke.v]
elaborate smoke
fdsc_dont_use
read_sdc [file join $here smoke.sdc]
syn_generic
syn_map
syn_opt
write_hdl > smoke_netlist.v
report_timing > genus_timing.rpt
report_area > genus_area.rpt
puts "SKY130CAD_GENUS_DONE"
exit
