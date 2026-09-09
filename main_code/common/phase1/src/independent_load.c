/* Matched dependency/parallelism diagnostic. Shared timers remain unchanged. */
#define main baseline_main
#include "cache_bench.c"
#undef main

/* Both loops issue four loads per iteration, with no timed-loop stack accesses.
 * Independent chains start one quarter-cycle apart in the same random ring. */
__attribute__((noinline)) static uintptr_t serial4(uintptr_t p, uint64_t rounds) {
#if defined(__x86_64__)
    __asm__ volatile("1: mov (%0),%0; mov (%0),%0; mov (%0),%0; mov (%0),%0; dec %1; jnz 1b"
                     : "+&r"(p), "+&r"(rounds) :: "cc", "memory");
#elif defined(__aarch64__)
    __asm__ volatile("1: ldr %0,[%0]; ldr %0,[%0]; ldr %0,[%0]; ldr %0,[%0]; subs %1,%1,#1; b.ne 1b"
                     : "+&r"(p), "+&r"(rounds) :: "cc", "memory");
#else
#error This diagnostic requires its audited x86-64 or AArch64 kernel
#endif
    return p;
}

__attribute__((noinline)) static uintptr_t parallel4(uintptr_t a, uintptr_t b,
                                                   uintptr_t c, uintptr_t d, uint64_t rounds) {
#if defined(__x86_64__)
    __asm__ volatile("1: mov (%0),%0; mov (%1),%1; mov (%2),%2; mov (%3),%3; dec %4; jnz 1b"
                     : "+&r"(a), "+&r"(b), "+&r"(c), "+&r"(d), "+&r"(rounds) :: "cc", "memory");
#elif defined(__aarch64__)
    __asm__ volatile("1: ldr %0,[%0]; ldr %1,[%1]; ldr %2,[%2]; ldr %3,[%3]; subs %4,%4,#1; b.ne 1b"
                     : "+&r"(a), "+&r"(b), "+&r"(c), "+&r"(d), "+&r"(rounds) :: "cc", "memory");
#endif
    return a ^ b ^ c ^ d;
}

int main(int argc, char **argv) {
    if (argc != 12) {
        fprintf(stderr,"usage: independent_load MODE BYTES STRIDE OFFSET SAMPLES BATCH SEED CPU ORDER RAW STREAMS\n");
        return 2;
    }
    const char *mode=argv[1];
    size_t bytes=number(argv[2]), stride=number(argv[3]);
    uint64_t samples=number(argv[5]), batch=number(argv[6]), seed=number(argv[7]), state=seed;
    int cpu=(int)number(argv[8]), streams=(int)number(argv[11]);
    if (bytes!=1024 || stride!=8 || number(argv[4])!=0 || !samples || samples>10000000 ||
        batch<128 || batch>32768 || batch%128 || !seed || cpu<0 || cpu>=CPU_SETSIZE ||
        (streams!=1 && streams!=4) || strcmp(argv[9],"random") ||
        (strcmp(mode,"chase") && strcmp(mode,"overhead") && strcmp(mode,"loop"))) return 2;
    cpu_set_t affinity; CPU_ZERO(&affinity); CPU_SET(cpu,&affinity);
    if (sched_setaffinity(0,sizeof(affinity),&affinity)) { perror("affinity"); return 3; }
    CPU_ZERO(&affinity);
    if (sched_getaffinity(0,sizeof(affinity),&affinity) || CPU_COUNT(&affinity)!=1 ||
        !CPU_ISSET(cpu,&affinity) || sched_getcpu()!=cpu) return 3;
    unsigned char *mem=mmap(NULL,bytes,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
    uint64_t *raw=calloc(samples,sizeof(*raw));
    if (mem==MAP_FAILED || !raw) return 4;
    int advice=madvise(mem,bytes,MADV_NOHUGEPAGE);
    memset(mem,0,bytes);
    for(uint64_t i=0;i<samples;i++) raw[i]=1;
    size_t n=bytes/stride, perm[128];
    for(size_t i=0;i<n;i++) perm[i]=i;
    for(size_t i=n-1;i>0;i--) { size_t j=rng(&state)%(i+1), t=perm[i]; perm[i]=perm[j]; perm[j]=t; }
    uint64_t ring_hash=14695981039346656037ULL;
    for(size_t i=0;i<n;i++) {
        *(uintptr_t *)(mem+perm[i]*stride)=(uintptr_t)(mem+perm[(i+1)%n]*stride);
        ring_hash=(ring_hash ^ perm[i])*1099511628211ULL;
    }
    uintptr_t a=(uintptr_t)(mem+perm[0]*stride), b=(uintptr_t)(mem+perm[n/4]*stride);
    uintptr_t c=(uintptr_t)(mem+perm[n/2]*stride), d=(uintptr_t)(mem+perm[3*n/4]*stride);
    /* Functional identity checks: both kernels visit exactly the expected nodes. */
    uintptr_t next4=(uintptr_t)(mem+perm[1]*stride) ^ (uintptr_t)(mem+perm[n/4+1]*stride) ^
                    (uintptr_t)(mem+perm[n/2+1]*stride) ^ (uintptr_t)(mem+perm[3*n/4+1]*stride);
    if (serial4(a,1)!=(uintptr_t)(mem+perm[4]*stride) || parallel4(a,b,c,d,1)!=next4 ||
        serial4(a,n/4)!=a || parallel4(a,b,c,d,n)!=(a^b^c^d)) return 6;
    uint64_t warm=0, start=mono();
    do {
        sink=streams==1 ? serial4(a,batch/4) : parallel4(a,b,c,d,batch/4);
        warm+=batch;
    } while(mono()-start<100000000ULL);
    struct rusage before,after; getrusage(RUSAGE_SELF,&before);
    uint64_t begin=mono();
    for(uint64_t i=0;i<samples;i++) {
        uint64_t lo=tick_start();
        if(!strcmp(mode,"chase"))
            sink=streams==1 ? serial4(a,batch/4) : parallel4(a,b,c,d,batch/4);
        else if(!strcmp(mode,"loop")) loop_control(batch/4);
        uint64_t hi=tick_stop(); raw[i]=hi-lo;
    }
    uint64_t elapsed=mono()-begin; getrusage(RUSAGE_SELF,&after);
    FILE *f=fopen(argv[10],"wb");
    if(!f || fwrite(raw,sizeof(*raw),samples,f)!=samples || fclose(f)) return 5;
    uint16_t endian=1;
#if defined(__x86_64__)
    const char *unit="TSC_ticks";
#else
    const char *unit="CNTVCT_ticks";
#endif
    printf("{\"mode\":\"%s\",\"streams\":%d,\"bytes\":%zu,\"stride\":%zu,\"samples\":%" PRIu64
           ",\"batch\":%" PRIu64 ",\"seed\":%" PRIu64 ",\"cpu\":%d,\"final_cpu\":%d,\"unit\":\"%s\""
           ",\"elapsed_ns\":%" PRIu64 ",\"warmup_loads\":%" PRIu64 ",\"ring_hash\":\"%016" PRIx64 "\""
           ",\"functional_checks_passed\":true,\"little_endian\":%s,\"major_faults\":%ld,\"minor_faults\":%ld"
           ",\"involuntary_switches\":%ld,\"voluntary_switches\":%ld,\"madvise_nohugepage_rc\":%d}\n",
           mode,streams,bytes,stride,samples,batch,seed,cpu,sched_getcpu(),unit,elapsed,warm,ring_hash,
           *(unsigned char*)&endian?"true":"false",after.ru_majflt-before.ru_majflt,after.ru_minflt-before.ru_minflt,
           after.ru_nivcsw-before.ru_nivcsw,after.ru_nvcsw-before.ru_nvcsw,advice);
    free(raw);munmap(mem,bytes);return 0;
}
