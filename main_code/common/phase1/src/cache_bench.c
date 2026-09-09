#define _GNU_SOURCE
#include <errno.h>
#include <inttypes.h>
#include <sched.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/resource.h>
#include <time.h>
#include <unistd.h>

/* Phase I: timers and ordinary loads only; no cache discovery interfaces. */
static volatile uintptr_t sink;
static uint64_t rng(uint64_t *s) {
    uint64_t x = *s; x ^= x << 13; x ^= x >> 7; x ^= x << 17;
    return *s = x;
}
static uint64_t mono(void) {
    struct timespec t; clock_gettime(CLOCK_MONOTONIC_RAW, &t);
    return (uint64_t)t.tv_sec * 1000000000ULL + t.tv_nsec;
}
static uint64_t tick_start(void) {
#if defined(FALLBACK_TIMER)
    return mono();
#elif defined(__x86_64__)
    uint32_t lo, hi;
    __asm__ volatile("lfence; rdtsc; lfence" : "=a"(lo), "=d"(hi) :: "memory");
    return ((uint64_t)hi << 32) | lo;
#elif defined(__aarch64__)
    uint64_t t;
    __asm__ volatile("dsb sy; isb; mrs %0, cntvct_el0; isb" : "=r"(t) :: "memory");
    return t;
#else
#error Unsupported ISA: build with -DFALLBACK_TIMER for CLOCK_MONOTONIC_RAW
#endif
}
static uint64_t tick_stop(void) {
#if defined(__x86_64__) && !defined(FALLBACK_TIMER)
    uint32_t lo, hi, aux;
    __asm__ volatile("rdtscp; lfence" : "=a"(lo), "=d"(hi), "=c"(aux) :: "memory");
    return ((uint64_t)hi << 32) | lo;
#else
    return tick_start();
#endif
}
/* Explicit register-only dependent loop avoids -O0 stack traffic inside the loop.
 * The entire program is still compiled at -O0. Assembly is saved and checked. */
__attribute__((noinline)) static uintptr_t chase(uintptr_t p, uint64_t n) {
#if defined(__x86_64__)
    __asm__ volatile("1: mov (%0), %0; dec %1; jnz 1b" : "+r"(p), "+r"(n) :: "cc", "memory");
#elif defined(__aarch64__)
    __asm__ volatile("1: ldr %0, [%0]; subs %1, %1, #1; b.ne 1b" : "+r"(p), "+r"(n) :: "cc", "memory");
#else
    while (n--) p = *(volatile uintptr_t *)p;
#endif
    return p;
}
__attribute__((noinline)) static void loop_control(uint64_t n) {
#if defined(__x86_64__)
    __asm__ volatile("1: dec %0; jnz 1b" : "+r"(n) :: "cc", "memory");
#elif defined(__aarch64__)
    __asm__ volatile("1: subs %0, %0, #1; b.ne 1b" : "+r"(n) :: "cc", "memory");
#else
    while (n--) __asm__ volatile("" ::: "memory");
#endif
}
static uint64_t number(const char *s) {
    char *e; errno=0; unsigned long long v=strtoull(s,&e,10);
    if (errno || !*s || *e || *s=='-') { fprintf(stderr,"Invalid integer: %s\n",s); exit(2); }
    return v;
}
int main(int argc, char **argv) {
    if (argc != 11) {
        fprintf(stderr,"usage: cache_bench MODE BYTES STRIDE OFFSET SAMPLES BATCH SEED CPU ORDER RAW\n"); return 2;
    }
    const char *mode=argv[1], *order=argv[9];
    size_t bytes=number(argv[2]), stride=number(argv[3]), offset=number(argv[4]);
    uint64_t samples=number(argv[5]), batch=number(argv[6]), seed=number(argv[7]), state=seed;
    int cpu=(int)number(argv[8]);
    if (!seed || !samples || samples>10000000 || !batch || cpu<0 || cpu>=CPU_SETSIZE ||
        stride<sizeof(uintptr_t) || stride%sizeof(uintptr_t) || bytes<stride*2 || bytes>1073741824ULL ||
        (strcmp(order,"random") && strcmp(order,"regular")) ||
        (strcmp(mode,"chase") && strcmp(mode,"spatial") && strcmp(mode,"reload") && strcmp(mode,"overhead") && strcmp(mode,"loop"))) return 2;
    if (!strcmp(mode,"spatial") && (offset<sizeof(uintptr_t) || offset%sizeof(uintptr_t) || offset+sizeof(uintptr_t)>stride)) return 2;
    cpu_set_t set; CPU_ZERO(&set); CPU_SET(cpu,&set);
    if(sched_setaffinity(0,sizeof(set),&set)) { perror("affinity"); return 3; }
    cpu_set_t actual; CPU_ZERO(&actual); sched_getaffinity(0,sizeof(actual),&actual);
    if(CPU_COUNT(&actual)!=1 || !CPU_ISSET(cpu,&actual) || sched_getcpu()!=cpu) return 3;
    /* All mappings are created and touched AFTER affinity: local first touch. */
    unsigned char *mem=mmap(NULL,bytes,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
    if(mem==MAP_FAILED) { perror("mmap"); return 4; }
    int huge_advice=madvise(mem,bytes,MADV_NOHUGEPAGE);
    memset(mem,0,bytes);
    size_t n=bytes/stride;
    size_t *perm=malloc(n*sizeof(*perm)); uint64_t *raw=calloc(samples,sizeof(*raw));
    if (!perm || !raw) { perror("allocation"); return 4; }
    /* Fault in raw pages before timing. */
    for(uint64_t i=0;i<samples;i++) raw[i]=1;
    for(size_t i=0;i<n;i++) perm[i]=i;
    if(!strcmp(order,"random")) for(size_t i=n-1;i>0;i--) {
        size_t j=rng(&state)%(i+1), t=perm[i]; perm[i]=perm[j]; perm[j]=t;
    }
    for(size_t i=0;i<n;i++) {
        uintptr_t *a=(uintptr_t *)(mem+perm[i]*stride);
        uintptr_t next=(uintptr_t)(mem+perm[(i+1)%n]*stride);
        if(!strcmp(mode,"spatial")) {
            *a=(uintptr_t)(mem+perm[i]*stride+offset); *(uintptr_t *)(mem+perm[i]*stride+offset)=next;
        } else *a=next;
    }
    uintptr_t p=(uintptr_t)(mem+perm[0]*stride); free(perm);
    uint64_t nodes=n*(!strcmp(mode,"spatial")?2:1), warm=nodes*2+batch;
    p=chase(p,warm);
    /* Independent target for eviction/reload diagnostic. Pressure is NOT assumed
       congruent or isolated from upper levels: global inclusion is never inferred. */
    uintptr_t *target=mmap(NULL,4096,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
    if(target==MAP_FAILED) return 4;
    *target=(uintptr_t)target;
    struct timespec pause={0,20000000};
    uint64_t m0=mono(), t0=tick_start(); nanosleep(&pause,NULL);
    uint64_t t1=tick_stop(), m1=mono();
    double hz=(double)(t1-t0)*1e9/(double)(m1-m0);
    uint64_t freq=0;
#if defined(__aarch64__) && !defined(FALLBACK_TIMER)
    __asm__ volatile("mrs %0, cntfrq_el0" : "=r"(freq));
#endif
    /* Stabilize wake-up/frequency ramp after timer calibration; excluded from samples. */
    uint64_t settle_start=mono(), settle_loads=0;
    do { p=chase(p,4096); settle_loads+=4096; } while(mono()-settle_start<100000000ULL);
    warm+=settle_loads;
    struct rusage r0,r1; getrusage(RUSAGE_SELF,&r0);
    int kind=!strcmp(mode,"loop")?1:!strcmp(mode,"reload")?2:!strcmp(mode,"overhead")?3:0;
    uint64_t begin=mono();
    for(uint64_t i=0;i<samples;i++) {
        if(kind==2) { sink=chase((uintptr_t)target,32); p=chase(p,batch); }
        uint64_t a=tick_start();
        if(kind==1) loop_control(batch);
        else if(kind==2) sink=chase((uintptr_t)target,1);
        else if(kind!=3) p=chase(p,batch);
        uint64_t b=tick_stop(); raw[i]=b-a;
    }
    uint64_t end=mono(); getrusage(RUSAGE_SELF,&r1); sink=p;
    FILE *out=fopen(argv[10],"wb");
    if(!out || fwrite(raw,sizeof(*raw),samples,out)!=samples || fclose(out)) { perror("raw output"); return 5; }
    uint16_t endian=1;
#if defined(FALLBACK_TIMER)
    const char *unit="monotonic_raw_ns";
#elif defined(__x86_64__)
    const char *unit="TSC_ticks";
#else
    const char *unit="CNTVCT_ticks";
#endif
    printf("{\"mode\":\"%s\",\"bytes\":%zu,\"stride\":%zu,\"offset\":%zu,\"nodes\":%" PRIu64 ",\"samples\":%" PRIu64 ",\"batch\":%" PRIu64 ",\"seed\":%" PRIu64 ",\"cpu\":%d,\"final_cpu\":%d,\"unit\":\"%s\",\"counter_frequency\":%" PRIu64 ",\"empirical_ticks_per_second\":%.3f,\"calibration_ns\":%" PRIu64 ",\"elapsed_ns\":%" PRIu64 ",\"warmup_loads\":%" PRIu64 ",\"alignment\":%ld,\"madvise_nohugepage_rc\":%d,\"little_endian\":%s,\"minor_faults\":%ld,\"major_faults\":%ld,\"voluntary_switches\":%ld,\"involuntary_switches\":%ld,\"address\":\"%p\"}\n",
        mode,bytes,stride,offset,nodes,samples,batch,seed,cpu,sched_getcpu(),unit,freq,hz,m1-m0,end-begin,warm,sysconf(_SC_PAGESIZE),huge_advice,*(unsigned char*)&endian?"true":"false",r1.ru_minflt-r0.ru_minflt,r1.ru_majflt-r0.ru_majflt,r1.ru_nvcsw-r0.ru_nvcsw,r1.ru_nivcsw-r0.ru_nivcsw,(void*)mem);
    free(raw); munmap(mem,bytes); munmap(target,4096); return 0;
}
