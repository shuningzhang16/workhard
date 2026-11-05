#ifndef DAQ_SESSION_H
#define DAQ_SESSION_H

#include "simple_s2mm.h"

enum { DAQ_CONTROL = 0x00, DAQ_STATUS = 0x04, DAQ_COMMAND = 0x08,
       DAQ_WORDS = 0x0c, DAQ_FRAMES = 0x10, DAQ_STALLS = 0x14 };
typedef struct {
    int (*read)(void *context, unsigned offset, uint32_t *value);
    int (*write)(void *context, unsigned offset, uint32_t value);
} daq_register_ops;
typedef enum {
    DAQ_OK, DAQ_DONE, DAQ_NEEDS_RESTART, DAQ_CONFIG_ERROR,
    DAQ_REGISTER_ERROR, DAQ_RECEIVE_ERROR, DAQ_STOP_LIMIT, DAQ_COUNT_ERROR
} daq_status;
typedef struct {
    simple_s2mm receiver;
    s2mm_ops dma_ops;
    daq_register_ops registers;
    void *context;
    daq_status status;
    bool start_pending, register_failed;
    uint32_t last_control_status, last_frames;
    unsigned drained;
} daq_session;

/* One caller owns both control MMIO and DMA. DMA resets acquisition state to
 * STOPPED/frame 0; AXI-Lite stays on the system reset as wired in create_bd.tcl.
 * MMIO callbacks finish before returning; no concurrent control ISR.
 */
daq_status daq_init(daq_session *session, const s2mm_ops *dma,
                    const daq_register_ops *registers, void *context,
                    const void *buffer, size_t capacity, unsigned poll_limit);
daq_status daq_restart(daq_session *session);
/* First receive arms DMA before writing START; later packets do not re-START. */
daq_status daq_receive(daq_session *session);
/* Nonblocking stop steps for a bounded consumer queue: check returns DAQ_OK
 * when another packet must be drained, DAQ_DONE only after both count checks.
 * The caller must bound its drain attempts; neither function receives data.
 */
daq_status daq_request_stop(daq_session *session);
daq_status daq_check_stop(daq_session *session, uint64_t requested_frames);
/* Request STOP, drain at most max_drain additional packets, then compare both
 * hardware frame count and the ORIGINAL requested count. No adjusted target.
 * STOP latency may produce an extra frame: that is reported, never hidden.
 */
daq_status daq_stop(daq_session *session, uint64_t requested_frames, unsigned max_drain);
const char *daq_status_name(daq_status status);

#endif
