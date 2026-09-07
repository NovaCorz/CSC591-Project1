#define _GNU_SOURCE
#include <assert.h>
#include <errno.h>
#include <inttypes.h>
#include <limits.h>
#include <sched.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

/* Phase I only: no PMU or cache-specification queries. */
#if defined(__x86_64__)
#include <x86intrin.h>
#define TIMER_UNIT "TSC ticks"
static uint64_t timer_start(void) {
    __asm__ volatile("" ::: "memory");
    _mm_lfence();
    uint64_t t = __rdtsc();
    _mm_lfence();
    __asm__ volatile("" ::: "memory");
    return t;
}
static uint64_t timer_stop(void) {
    unsigned aux;
    __asm__ volatile("" ::: "memory");
    uint64_t t = __rdtscp(&aux);
    _mm_lfence();
    __asm__ volatile("" ::: "memory");
    return t;
}
static uint64_t timer_frequency(void) { return 0; }
#elif defined(__aarch64__)
#define TIMER_UNIT "Arm counter ticks"
static uint64_t timer_start(void) {
    uint64_t t;
    __asm__ volatile("dsb sy\n\tisb\n\tmrs %0, cntvct_el0\n\tisb"
                     : "=r"(t) :: "memory");
    return t;
}
static uint64_t timer_stop(void) { return timer_start(); }
static uint64_t timer_frequency(void) {
    uint64_t f;
    __asm__ volatile("mrs %0, cntfrq_el0" : "=r"(f));
    return f;
}
#else
#error "This benchmark supports Linux x86-64 and AArch64."
#endif

static void fail(const char *message) {
    fprintf(stderr, "%s\n", message);
    exit(EXIT_FAILURE);
}

static size_t number(const char *s) {
    char *end;
    errno = 0;
    unsigned long long v = strtoull(s, &end, 10);
    if (!*s || *s == '-' || *s == '+' || errno || *end || !v || v > SIZE_MAX)
        fail("Arguments must be positive decimal integers within size_t range.");
    return (size_t)v;
}

/* Fixed seed makes the address order reproducible; this is not cryptographic. */
static uint64_t random64(uint64_t *state) {
    uint64_t x = *state;
    x ^= x >> 12;
    x ^= x << 25;
    x ^= x >> 27;
    *state = x;
    return x * UINT64_C(2685821657736338717);
}

static uint64_t bounded_random(uint64_t *state, uint64_t bound) {
    uint64_t x, threshold = -bound % bound;
    do { x = random64(state); } while (x < threshold);
    return x % bound;
}

static void *make_cycle(unsigned char *memory, size_t bytes, size_t spacing,
                        uint64_t seed, int randomized) {
    size_t n = bytes / spacing;
    size_t *order = malloc(n * sizeof(*order));
    if (!order) fail("Cannot allocate shuffle array; use a smaller footprint.");
    for (size_t i = 0; i < n; ++i) order[i] = i;
    if (randomized) {
        for (size_t i = n - 1; i > 0; --i) {
            size_t j = bounded_random(&seed, i + 1);
            size_t tmp = order[i]; order[i] = order[j]; order[j] = tmp;
        }
    }
    for (size_t i = 0; i < n; ++i)
        *(void **)(memory + order[i] * spacing) =
            memory + order[(i + 1) % n] * spacing;
    void *start = memory + order[0] * spacing;
    free(order);
    /* Check the full cycle, and touch all its nodes before measurement. */
    void *p = start;
    for (size_t i = 0; i < n; ++i) {
        p = *(void **)p;
        assert((i + 1 == n) == (p == start));
    }
    return start;
}

/* Explicit register loop keeps -O0 from spilling p/i to the stack per load.
 * Each load's address is the previous load's result. No stores in this loop.
 * The function-call and loop overhead remain; test sensitivity to batch size.
 */
__attribute__((noinline)) static void *chase(void *p, size_t steps) {
    assert(steps > 0);
#if defined(__x86_64__)
    __asm__ volatile("1:\n\tmov (%0), %0\n\tdec %1\n\tjnz 1b"
                     : "+&r"(p), "+&r"(steps) :: "cc", "memory");
#else
    __asm__ volatile("1:\n\tldr %0, [%0]\n\tsubs %1, %1, #1\n\tb.ne 1b"
                     : "+&r"(p), "+&r"(steps) :: "cc", "memory");
#endif
    return p;
}

static void *volatile sink;

int main(int argc, char **argv) {
    if (argc != 8) {
        fprintf(stderr, "Usage: %s BYTES SPACING SAMPLES STEPS SEED random|sequential|empty OUTPUT.bin\n",
                argv[0]);
        return EXIT_FAILURE;
    }
    size_t bytes = number(argv[1]), spacing = number(argv[2]);
    size_t samples = number(argv[3]), steps = number(argv[4]);
    uint64_t seed = number(argv[5]);
    int randomized = strcmp(argv[6], "random") == 0;
    int empty = strcmp(argv[6], "empty") == 0;
    if (!randomized && !empty && strcmp(argv[6], "sequential") != 0)
        fail("Mode must be random, sequential, or empty.");
    if (spacing < sizeof(void *) || spacing % sizeof(void *) ||
        bytes % spacing || bytes / spacing < 2 || samples > SIZE_MAX / sizeof(uint64_t))
        fail("Use pointer-aligned spacing, a divisible footprint with >=2 nodes, and a valid sample count.");
    cpu_set_t cpus;
    if (sched_getaffinity(0, sizeof(cpus), &cpus) != 0) {
        perror("sched_getaffinity"); return EXIT_FAILURE;
    }
    if (CPU_COUNT(&cpus) != 1) fail("Pin to exactly one logical CPU using taskset -c CPU.");
    long page_size = sysconf(_SC_PAGESIZE);
    if (page_size <= 0) fail("Cannot determine OS page size.");
    unsigned char *memory = NULL;
    if (posix_memalign((void **)&memory, (size_t)page_size, bytes) != 0)
        fail("Cannot allocate footprint; reduce size or check memory limits.");
    uint64_t *raw = malloc(samples * sizeof(*raw));
    if (!raw) fail("Cannot allocate raw sample buffer.");
    /* First-touch occurs after affinity; fault output pages before timing. */
    memset(memory, 0, bytes);
    memset(raw, 0, samples * sizeof(*raw));
    void *p = make_cycle(memory, bytes, spacing, seed, randomized);
    size_t nodes = bytes / spacing;
    p = chase(p, nodes);
    p = chase(p, nodes);
    uint64_t frequency = timer_frequency();
    FILE *out = fopen(argv[7], "wbx");
    if (!out) { perror(argv[7]); return EXIT_FAILURE; }
    /* Separate empty/full loops: no mode branch in the timed region. */
    for (size_t i = 0; i < samples; ++i) {
        uint64_t t0, t1;
        if (empty) {
            t0 = timer_start();
            t1 = timer_stop();
        } else {
            t0 = timer_start();
            p = chase(p, steps);
            t1 = timer_stop();
        }
        if (t1 < t0) fail("Timer moved backwards; discard this run.");
        raw[i] = t1 - t0;
    }
    sink = p;
    if (fwrite(raw, sizeof(*raw), samples, out) != samples) {
        perror("write samples"); return EXIT_FAILURE;
    }
    if (fclose(out) != 0) { perror("close samples"); return EXIT_FAILURE; }
    uint16_t endian = 1;
    printf("{\"bytes\":%zu,\"spacing\":%zu,\"nodes\":%zu,\"samples\":%zu,"
           "\"steps\":%zu,\"seed\":%" PRIu64 ",\"mode\":\"%s\","
           "\"unit\":\"%s\",\"timer_hz\":%" PRIu64 ",\"cpu\":%d,"
           "\"page_size\":%ld,\"warmup_steps\":%zu,\"byte_order\":\"%s\"}\n",
           bytes, spacing, nodes, samples, steps, seed, argv[6], TIMER_UNIT,
           frequency, sched_getcpu(), page_size, 2 * nodes,
           *(unsigned char *)&endian ? "little" : "big");
    free(raw);
    free(memory);
    return EXIT_SUCCESS;
}
