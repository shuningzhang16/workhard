/* Reader for the experiment's existing plain, unquoted 15-column sample CSV.
 * Only measured Vin/vO/iL and clear_request drive the C controller. */
#include "buck_control.h"

#include <errno.h>
#include <inttypes.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static bool number(const char *text, double *value)
{
    char *end;
    errno = 0;
    *value = strtod(text, &end);
    return errno == 0 && end != text && *end == '\0' && isfinite(*value);
}

int main(int argc, char **argv)
{
    const char *header = "time_s,input_v,load_ohm,output_v,inductor_current_a,load_current_a,stored_energy_j,injection_active,clear_request,duty,reference_v,state,active_faults,latched_fault,clear_result";
    FILE *input;
    FILE *output;
    char line[1024];
    uint64_t sample = 0;
    BuckController control;
    int status = EXIT_SUCCESS;
    if (argc != 3) {
        fprintf(stderr, "usage: replay_csv input_control_samples.csv output_c.csv\n");
        return EXIT_FAILURE;
    }
    input = fopen(argv[1], "r");
    if (input == NULL) {
        perror(argv[1]);
        return EXIT_FAILURE;
    }
    output = fopen(argv[2], "w");
    if (output == NULL) {
        perror(argv[2]);
        (void)fclose(input);
        return EXIT_FAILURE;
    }
    if (fgets(line, (int)sizeof(line), input) == NULL) {
        status = EXIT_FAILURE;
    } else {
        line[strcspn(line, "\r\n")] = '\0';
        if (strcmp(line, header) != 0) {
            fprintf(stderr, "unexpected sample CSV header\n");
            status = EXIT_FAILURE;
        }
    }
    buck_controller_init(&control);
    fprintf(output, "sample,duty,reference_v,state,active_faults,latched_fault,clear_result\n");
    while (status == EXIT_SUCCESS && fgets(line, (int)sizeof(line), input) != NULL) {
        char *fields[15];
        size_t count = 1;
        double time_s, input_v, output_v, current_a, clear_value;
        BuckCommand command;
        fields[0] = line;
        line[strcspn(line, "\r\n")] = '\0';
        for (char *cursor = line; *cursor != '\0'; ++cursor) {
            if (*cursor == ',') {
                *cursor = '\0';
                if (count < 15U) {
                    fields[count] = cursor + 1;
                }
                ++count;
            }
        }
        if (count != 15U || !number(fields[0], &time_s) || !number(fields[1], &input_v)
            || !number(fields[3], &output_v) || !number(fields[4], &current_a)
            || !number(fields[8], &clear_value) || (clear_value != 0.0 && clear_value != 1.0)
            || fabs(time_s - (double)sample * BUCK_TS_S) > 1e-12) {
            fprintf(stderr, "invalid measurement row at sample %" PRIu64 "\n", sample);
            status = EXIT_FAILURE;
            break;
        }
        command = buck_controller_step(&control, sample, input_v, output_v, current_a, clear_value == 1.0);
        fprintf(output, "%" PRIu64 ",%.17g,%.17g,%d,%u,%u,%d\n", sample,
                command.duty, command.reference_v, (int)command.state,
                command.active_faults, command.latched_fault, (int)command.clear_result);
        ++sample;
    }
    if (ferror(input) != 0 || ferror(output) != 0) {
        status = EXIT_FAILURE;
    }
    if (fclose(input) != 0) {
        status = EXIT_FAILURE;
    }
    if (fclose(output) != 0) {
        status = EXIT_FAILURE;
    }
    printf("replayed_samples=%" PRIu64 " status=%d\n", sample, status);
    return status;
}
