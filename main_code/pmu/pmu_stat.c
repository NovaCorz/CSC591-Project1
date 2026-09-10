/*
 * pmu_stat.c -- portable Phase-II counter wrapper for HW1.
 *
 * Launches an unmodified child program (your frozen Phase-I benchmark)
 * exactly like `perf stat -- cmd`, attaches a *group* of hardware
 * performance-counter events to that specific process, and prints a
 * CSV line with raw counts plus time_enabled/time_running so you can
 * detect multiplexing.
 *
 * Why this design: it never touches your Phase-I benchmark source, so
 * the timing-only code you froze stays byte-for-byte identical. It
 * works the same way on Intel, AMD, and Arm because it uses the
 * generic PERF_TYPE_HARDWARE and PERF_TYPE_HW_CACHE event abstractions
 * that the kernel maps onto whatever raw PMU events exist per vendor.
 *
 * Build:
 *   gcc -O2 -o pmu_stat pmu_stat.c
 *   (Note: -O2 is fine here -- this is a measurement HARNESS, not the
 *    Phase-I benchmark itself. Your child program is still whatever
 *    -O0 binary you froze.)
 *
 * Usage:
 *   ./pmu_stat -e cycles,instructions,L1D-read-access,L1D-read-miss,\
 *                 LL-read-access,LL-read-miss,dTLB-read-miss,cache-misses \
 *              -- taskset -c 4 ./cache_bench capacity 65536
 *
 * Output (stdout, CSV, one line):
 *   event1_count,event1_enabled_ns,event1_running_ns,event2_count,...
 * plus a human-readable summary on stderr.
 *
 * Supported generic event names (PERF_TYPE_HARDWARE):
 *   cycles, instructions, cache-references, cache-misses,
 *   branch-instructions, branch-misses, bus-cycles, ref-cycles
 *
 * Supported cache-event names (PERF_TYPE_HW_CACHE), pattern
 *   <CACHE>-<OP>-<RESULT> where:
 *     CACHE  = L1D | L1I | LL | DTLB | ITLB | BPU | NODE
 *     OP     = read | write | prefetch
 *     RESULT = access | miss
 *   e.g. L1D-read-miss, LL-write-access, dTLB-read-miss
 *
 * If the kernel/PMU does not expose a requested event, perf_event_open
 * fails for that event; this tool records it as UNAVAILABLE rather
 * than crashing, so partial coverage on Arm (which often lacks a full
 * cache-event set) does not stop the run.
 */

#define _GNU_SOURCE
#include <errno.h>
#include <inttypes.h>
#include <linux/perf_event.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <unistd.h>

#define MAX_EVENTS 16

typedef struct {
    char name[64];
    int  type;      /* PERF_TYPE_HARDWARE or PERF_TYPE_HW_CACHE */
    uint64_t config;
    int  fd;
    int  available;
} pmc_event_t;

static long perf_event_open(struct perf_event_attr *attr, pid_t pid,
                             int cpu, int group_fd, unsigned long flags) {
    return syscall(SYS_perf_event_open, attr, pid, cpu, group_fd, flags);
}

/* ---- name -> (type, config) resolution ---- */

static int hw_generic_config(const char *name, uint64_t *cfg) {
    if (!strcmp(name, "cycles"))              { *cfg = PERF_COUNT_HW_CPU_CYCLES; return 1; }
    if (!strcmp(name, "instructions"))         { *cfg = PERF_COUNT_HW_INSTRUCTIONS; return 1; }
    if (!strcmp(name, "cache-references"))     { *cfg = PERF_COUNT_HW_CACHE_REFERENCES; return 1; }
    if (!strcmp(name, "cache-misses"))         { *cfg = PERF_COUNT_HW_CACHE_MISSES; return 1; }
    if (!strcmp(name, "branch-instructions"))  { *cfg = PERF_COUNT_HW_BRANCH_INSTRUCTIONS; return 1; }
    if (!strcmp(name, "branch-misses"))        { *cfg = PERF_COUNT_HW_BRANCH_MISSES; return 1; }
    if (!strcmp(name, "bus-cycles"))           { *cfg = PERF_COUNT_HW_BUS_CYCLES; return 1; }
    if (!strcmp(name, "ref-cycles"))           { *cfg = PERF_COUNT_HW_REF_CPU_CYCLES; return 1; }
    return 0;
}

static int cache_id_from_str(const char *s, uint64_t *id) {
    if (!strcmp(s, "L1D"))  { *id = PERF_COUNT_HW_CACHE_L1D;  return 1; }
    if (!strcmp(s, "L1I"))  { *id = PERF_COUNT_HW_CACHE_L1I;  return 1; }
    if (!strcmp(s, "LL"))   { *id = PERF_COUNT_HW_CACHE_LL;   return 1; }
    if (!strcmp(s, "DTLB")) { *id = PERF_COUNT_HW_CACHE_DTLB; return 1; }
    if (!strcmp(s, "ITLB")) { *id = PERF_COUNT_HW_CACHE_ITLB; return 1; }
    if (!strcmp(s, "BPU"))  { *id = PERF_COUNT_HW_CACHE_BPU;  return 1; }
    if (!strcmp(s, "NODE")) { *id = PERF_COUNT_HW_CACHE_NODE; return 1; }
    return 0;
}

static int hw_cache_config(const char *name, uint64_t *cfg) {
    /* pattern: <CACHE>-<op>-<result> */
    char buf[64];
    strncpy(buf, name, sizeof(buf) - 1);
    buf[sizeof(buf) - 1] = '\0';

    char *cache_s = strtok(buf, "-");
    char *op_s    = strtok(NULL, "-");
    char *res_s   = strtok(NULL, "-");
    if (!cache_s || !op_s || !res_s) return 0;

    uint64_t cache_id;
    if (!cache_id_from_str(cache_s, &cache_id)) return 0;

    uint64_t op_id;
    if (!strcmp(op_s, "read"))      op_id = PERF_COUNT_HW_CACHE_OP_READ;
    else if (!strcmp(op_s, "write"))    op_id = PERF_COUNT_HW_CACHE_OP_WRITE;
    else if (!strcmp(op_s, "prefetch")) op_id = PERF_COUNT_HW_CACHE_OP_PREFETCH;
    else return 0;

    uint64_t res_id;
    if (!strcmp(res_s, "access"))      res_id = PERF_COUNT_HW_CACHE_RESULT_ACCESS;
    else if (!strcmp(res_s, "miss"))   res_id = PERF_COUNT_HW_CACHE_RESULT_MISS;
    else return 0;

    *cfg = cache_id | (op_id << 8) | (res_id << 16);
    return 1;
}

static int resolve_event(pmc_event_t *ev) {
    uint64_t cfg;
    if (hw_generic_config(ev->name, &cfg)) {
        ev->type = PERF_TYPE_HARDWARE;
        ev->config = cfg;
        return 1;
    }
    if (hw_cache_config(ev->name, &cfg)) {
        ev->type = PERF_TYPE_HW_CACHE;
        ev->config = cfg;
        return 1;
    }
    return 0;
}

/* ---- open one event, attached to pid, as part of a group ---- */
static int open_event(pmc_event_t *ev, pid_t pid, int group_fd, int is_leader) {
    struct perf_event_attr pe;
    memset(&pe, 0, sizeof(pe));
    pe.type = ev->type;
    pe.size = sizeof(pe);
    pe.config = ev->config;
    pe.disabled = is_leader;   /* leader starts disabled; group enabled together */
    pe.exclude_kernel = 1;
    pe.exclude_hv = 1;
    pe.read_format = PERF_FORMAT_GROUP |
                      PERF_FORMAT_TOTAL_TIME_ENABLED |
                      PERF_FORMAT_TOTAL_TIME_RUNNING;
    int fd = (int)perf_event_open(&pe, pid, -1, group_fd, 0);
    return fd;
}

static void split_events(char *spec, pmc_event_t *events, int *n) {
    char *tok = strtok(spec, ",");
    *n = 0;
    while (tok && *n < MAX_EVENTS) {
        strncpy(events[*n].name, tok, sizeof(events[*n].name) - 1);
        (*n)++;
        tok = strtok(NULL, ",");
    }
}

int main(int argc, char **argv) {
    if (argc < 4 || strcmp(argv[1], "-e") != 0) {
        fprintf(stderr,
            "usage: %s -e ev1,ev2,... -- <command> [args...]\n", argv[0]);
        return 1;
    }

    char *event_spec = argv[2];
    int sep = 3; /* index of "--" */
    if (strcmp(argv[sep], "--") != 0) {
        fprintf(stderr, "expected -- before command\n");
        return 1;
    }
    char **child_argv = &argv[sep + 1];
    if (!child_argv[0]) {
        fprintf(stderr, "no command given after --\n");
        return 1;
    }

    pmc_event_t events[MAX_EVENTS];
    int n_events = 0;
    split_events(event_spec, events, &n_events);
    if (n_events == 0) {
        fprintf(stderr, "no events parsed\n");
        return 1;
    }
    for (int i = 0; i < n_events; i++) {
        events[i].fd = -1;
        events[i].available = resolve_event(&events[i]);
        if (!events[i].available) {
            fprintf(stderr, "warning: unrecognized event name '%s'\n",
                    events[i].name);
        }
    }

    pid_t pid = fork();
    if (pid < 0) { perror("fork"); return 1; }

    if (pid == 0) {
        /* child: stop itself, exec once parent has attached counters */
        raise(SIGSTOP);
        execvp(child_argv[0], child_argv);
        perror("execvp");
        _exit(127);
    }

    /* parent: wait for the child to stop itself (post-fork, pre-exec) */
    int status;
    waitpid(pid, &status, WUNTRACED);
    if (!WIFSTOPPED(status)) {
        fprintf(stderr, "child did not stop as expected\n");
        return 1;
    }

    int group_leader_fd = -1;
    for (int i = 0; i < n_events; i++) {
        if (!events[i].available) continue;
        int is_leader = (group_leader_fd == -1);
        int fd = open_event(&events[i], pid, is_leader ? -1 : group_leader_fd,
                             is_leader);
        if (fd < 0) {
            fprintf(stderr, "perf_event_open failed for '%s': %s "
                    "(check /proc/sys/kernel/perf_event_paranoid, or this "
                    "event may not be exposed on this PMU)\n",
                    events[i].name, strerror(errno));
            events[i].available = 0;
            continue;
        }
        events[i].fd = fd;
        if (is_leader) group_leader_fd = fd;
    }

    if (group_leader_fd < 0) {
        fprintf(stderr, "no events opened successfully; aborting run\n");
        kill(pid, SIGKILL);
        return 1;
    }

    ioctl(group_leader_fd, PERF_EVENT_IOC_RESET, PERF_IOC_FLAG_GROUP);
    ioctl(group_leader_fd, PERF_EVENT_IOC_ENABLE, PERF_IOC_FLAG_GROUP);

    /* let the child run the actual workload */
    kill(pid, SIGCONT);
    waitpid(pid, &status, 0);

    ioctl(group_leader_fd, PERF_EVENT_IOC_DISABLE, PERF_IOC_FLAG_GROUP);

    /* read the whole group in one call */
    size_t buf_sz = sizeof(uint64_t) * (3 + 2 * n_events);
    uint64_t *buf = calloc(1, buf_sz);
    ssize_t rd = read(group_leader_fd, buf, buf_sz);
    if (rd < 0) { perror("read"); return 1; }

    uint64_t time_enabled = buf[1];
    uint64_t time_running = buf[2];

    fprintf(stderr, "-- pmu_stat result --\n");
    fprintf(stderr, "child exit status: %d\n",
            WIFEXITED(status) ? WEXITSTATUS(status) : -1);
    fprintf(stderr, "time_enabled=%" PRIu64 " ns  time_running=%" PRIu64
            " ns  (%.1f%% -- <100%% means multiplexing occurred; "
            "reduce event count and re-run)\n",
            time_enabled, time_running,
            time_enabled ? (100.0 * time_running / time_enabled) : 0.0);

    /* CSV line: name=value pairs for whichever events actually opened */
    int idx = 0;
    for (int i = 0; i < n_events; i++) {
        if (!events[i].available) {
            printf("%s=UNAVAILABLE,", events[i].name);
            continue;
        }
        uint64_t val = buf[3 + idx];
        printf("%s=%" PRIu64 ",", events[i].name, val);
        idx++;
    }
    printf("time_enabled_ns=%" PRIu64 ",time_running_ns=%" PRIu64 "\n",
           time_enabled, time_running);

    for (int i = 0; i < n_events; i++) {
        if (events[i].fd >= 0) close(events[i].fd);
    }
    free(buf);
    return WIFEXITED(status) ? WEXITSTATUS(status) : 1;
}