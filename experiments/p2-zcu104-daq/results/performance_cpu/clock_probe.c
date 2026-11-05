#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <inttypes.h>
#include <stdio.h>
#include <sys/resource.h>
#include <time.h>

static uint64_t ns(clockid_t clock)
{
    struct timespec value;
    assert(clock_gettime(clock, &value) == 0);
    return (uint64_t)value.tv_sec * UINT64_C(1000000000) + (uint64_t)value.tv_nsec;
}
static uint64_t usage_us(const struct rusage *value)
{
    return (uint64_t)(value->ru_utime.tv_sec + value->ru_stime.tv_sec) * UINT64_C(1000000)
        + (uint64_t)(value->ru_utime.tv_usec + value->ru_stime.tv_usec);
}
int main(void)
{
    struct timespec resolution;
    assert(clock_getres(CLOCK_MONOTONIC, &resolution) == 0);
    printf("monotonic_reported_resolution_ns=%ld\n", resolution.tv_nsec);
    assert(clock_getres(CLOCK_PROCESS_CPUTIME_ID, &resolution) == 0);
    printf("process_reported_resolution_ns=%ld\n", resolution.tv_nsec);
    puts("mode,wall_ns,process_ns,thread_ns,rusage_us,process_pct");
    for (unsigned i = 0; i < 4; ++i) {
        struct rusage before, after;
        uint64_t wall = ns(CLOCK_MONOTONIC);
        uint64_t process = ns(CLOCK_PROCESS_CPUTIME_ID);
        uint64_t thread = ns(CLOCK_THREAD_CPUTIME_ID);
        assert(getrusage(RUSAGE_SELF, &before) == 0);
        if (i == 3) {
            struct timespec request = {0, 100000000};
            assert(nanosleep(&request, NULL) == 0);
        } else {
            while (ns(CLOCK_MONOTONIC) - wall < UINT64_C(100000000)) { }
        }
        assert(getrusage(RUSAGE_SELF, &after) == 0);
        thread = ns(CLOCK_THREAD_CPUTIME_ID) - thread;
        process = ns(CLOCK_PROCESS_CPUTIME_ID) - process;
        wall = ns(CLOCK_MONOTONIC) - wall;
        printf("%s,%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%.3f\n",
               i == 3 ? "sleep" : "busy", wall, process, thread,
               usage_us(&after) - usage_us(&before), 100.0 * (double)process / (double)wall);
    }
    return 0;
}
