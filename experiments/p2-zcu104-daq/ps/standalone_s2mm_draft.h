#ifndef STANDALONE_S2MM_DRAFT_H
#define STANDALONE_S2MM_DRAFT_H

/* UNCOMPILED integration draft: requires a generated, matching Standalone BSP. */
#include "simple_s2mm.h"
#include "xaxidma.h"

typedef struct {
    XAxiDma *dma;                /* Already initialized from real BSP config. */
    void *cpu_buffer;            /* Same pointer passed to s2mm_init. */
    UINTPTR dma_address;         /* Supplied mapping; never infer from CPU pointer. */
    u32 allocation_bytes;       /* Whole exclusively owned, cache-line aligned span. */
    u32 last_status;
    u32 last_submit_result;
} standalone_s2mm_context;

/* Before using these operations, validate the reset topology in vivado/README:
 * DMA s2mm_prmry_reset_out_n must reset source/FIFO to frame 0. No other user may
 * share this DMA engine: a soft reset resets BOTH channels. This draft does not
 * establish BSP, mappings, cache alignment, reset propagation or clock readiness.
 */
extern const s2mm_ops standalone_s2mm_ops;

#endif
