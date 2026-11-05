# Run only in the real, assigned/validated BD via create_project.tcl.
# No guessed addresses or synthetic header is emitted by the host text checker.
set address_csv [open [file join $build_dir address_map.csv] w]
set address_header [open [file join $build_dir daq_addresses.h] w]
puts $address_csv "role,slave_segment,master_segment,base,range"
puts $address_header "/* Generated from the current Vivado BD; not a BSP or DDR allocation. */"
puts $address_header "#ifndef DAQ_ADDRESSES_H\n#define DAQ_ADDRESSES_H\n#include <stdint.h>"
foreach {role pin macro_name} {
    control stream/S_AXI DAQ_CTRL_BASE_ADDRESS
    dma dma/S_AXI_LITE DAQ_DMA_BASE_ADDRESS
} {
    set slaves [get_bd_addr_segs -of_objects [get_bd_intf_pins $pin]]
    set maps [get_bd_addr_segs -addressing -of_objects $slaves]
    if {[llength $slaves] != 1 || [llength $maps] != 1} {
        error "Expected one assigned PS address for $pin; inspect the actual BD address map."
    }
    set mapping [lindex $maps 0]
    set base [get_property OFFSET $mapping]
    set span [get_property RANGE $mapping]
    puts $address_csv "$role,$slaves,$mapping,$base,$span"
    puts $address_header "#define $macro_name UINT64_C([format 0x%X $base])"
}
puts $address_header "#endif"
close $address_header
close $address_csv
puts "Exported actual assigned control/DMA addresses to $build_dir; BSP and DDR buffer allocation remain required."
