#define main baseline_benchmark_main
#include "cache_bench.c"
#undef main
#include <pthread.h>
#include <stdatomic.h>

/* Phase-I extension. The included source supplies only the same ordinary-load
 * kernels and architectural timers. Alignment and page policy are experimental
 * variables; no CPU cache-description interface is used. */
static unsigned long huge_kib(void *address) {
    FILE *f=fopen("/proc/self/smaps","r");
    char line[512]; int matched=0; unsigned long value=0;
    if(!f) return 0;
    while(fgets(line,sizeof(line),f)) {
        unsigned long start,end,n;
        if(sscanf(line,"%lx-%lx",&start,&end)==2) {
            if(matched) break;
            matched=(uintptr_t)address>=start && (uintptr_t)address<end;
        } else if(matched && sscanf(line,"AnonHugePages: %lu kB",&n)==1) value=n;
    }
    fclose(f); return value;
}
static unsigned char *mapping(size_t bytes, int huge, size_t *length) {
    size_t page=(size_t)sysconf(_SC_PAGESIZE);
    if(huge) {
        FILE *f=fopen("/sys/kernel/mm/transparent_hugepage/hpage_pmd_size","r");
        unsigned long n=0;
        if(f) { if(fscanf(f,"%lu",&n)!=1) n=0; fclose(f); }
        if(!n || (n&(n-1)) || n>67108864) return MAP_FAILED;
        page=n;
    }
    *length=(bytes+page-1)/page*page;
    size_t reserve=*length+page;
    unsigned char *raw=mmap(NULL,reserve,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
    if(raw==MAP_FAILED) return raw;
    uintptr_t a=((uintptr_t)raw+page-1)&~(uintptr_t)(page-1);
    size_t prefix=a-(uintptr_t)raw,suffix=reserve-prefix-*length;
    if(prefix) munmap(raw,prefix);
    if(suffix) munmap((void *)(a+*length),suffix);
    unsigned char *mem=(unsigned char *)a;
    if(madvise(mem,*length,huge?MADV_HUGEPAGE:MADV_NOHUGEPAGE)) {
        munmap(mem,*length); return MAP_FAILED;
    }
    memset(mem,0,*length); return mem;
}
typedef struct {
    _Alignas(1024) atomic_uint request;
    _Alignas(1024) atomic_uint done;
    _Alignas(1024) atomic_int ready;
    uintptr_t p;
    uint64_t loads;
    int cpu;
} helper_state;
static void *helper(void *arg) {
    helper_state *h=arg;
    cpu_set_t mask; CPU_ZERO(&mask); CPU_SET(h->cpu,&mask);
    if(sched_setaffinity(0,sizeof(mask),&mask)) { atomic_store(&h->ready,-1); return NULL; }
    uintptr_t p=h->p;
    atomic_store(&h->ready,1);
    unsigned previous=0;
    for(;;) {
        unsigned seq=atomic_load_explicit(&h->request,memory_order_acquire);
        if(seq==UINT32_MAX) break;
        if(seq!=previous) {
            if(h->loads) p=chase(p,h->loads);
            previous=seq;
            atomic_store_explicit(&h->done,seq,memory_order_release);
        }
    }
    h->p=p; return NULL;
}
int main(int argc,char **argv) {
    if(argc!=15) {
        fprintf(stderr,"usage: followup MODE BYTES STRIDE OFFSET SAMPLES BATCH SEED CPU ORDER RAW ALIGN PAGE_POLICY ADDRESS_LIST HELPER_CPU\n");
        return 2;
    }
    const char *mode=argv[1],*order=argv[9];
    size_t bytes=number(argv[2]),stride=number(argv[3]),offset=number(argv[4]),align=number(argv[11]);
    uint64_t samples=number(argv[5]),batch=number(argv[6]),seed=number(argv[7]),state=seed;
    int cpu=(int)number(argv[8]),is_spatial=!strcmp(mode,"spatial"),is_probe=!strcmp(mode,"probe"),is_cross=!strcmp(mode,"cross");
    int is_hot=!strcmp(mode,"hot"),is_empty=!strcmp(mode,"overhead"),huge=!strcmp(argv[12],"huge");
    int helper_cpu=atoi(argv[14]);
    if(!seed || !samples || samples>10000000 || !batch || cpu<0 || cpu>=CPU_SETSIZE ||
       stride<8 || stride%8 || bytes<stride*2 || bytes>536870912 || align%8 || align>4096 ||
       (strcmp(argv[12],"base") && !huge) || (strcmp(order,"random") && strcmp(order,"regular")) ||
       (strcmp(mode,"chase") && !is_spatial && !is_probe && !is_cross && !is_hot && !is_empty)) return 2;
    if(is_spatial && (offset<8 || offset%8 || align+offset+8>stride)) return 2;
    if(is_cross && (helper_cpu<0 || helper_cpu>=CPU_SETSIZE || helper_cpu==cpu)) return 2;
    cpu_set_t mask; CPU_ZERO(&mask); CPU_SET(cpu,&mask);
    if(sched_setaffinity(0,sizeof(mask),&mask)) { perror("affinity"); return 3; }
    size_t mapped=0;
    unsigned char *mem=mapping(bytes+align+8,huge,&mapped);
    if(mem==MAP_FAILED) { perror("mapping"); return 4; }
    size_t n=bytes/stride,*positions=malloc((n+1)*sizeof(size_t));
    uint64_t *raw=malloc(samples*sizeof(uint64_t));
    if(!positions || !raw) return 4;
    if(strcmp(argv[13],"-")) {
        FILE *f=fopen(argv[13],"r"); size_t at=0,v;
        if(!f) return 2;
        while(fscanf(f,"%zu",&v)==1) {
            if(at>=n || v%8 || v+8>bytes || ((is_probe||is_cross)&&v==0)) { fclose(f); return 2; }
            for(size_t j=0;j<at;j++) if(positions[j]==v) { fclose(f); return 2; }
            positions[at++]=v;
        }
        fclose(f); n=at;
        if(!n) return 2;
    } else for(size_t i=0;i<n;i++) positions[i]=i*stride;
    /* A probe's target is outside the pressure mapping unless an explicit list
       selects a target-relative pressure set. Both conditions are recorded. */
    uintptr_t *target;
    size_t target_length=0;
    if(strcmp(argv[13],"-")==0) {
        target=(uintptr_t *)mapping(4096,0,&target_length);
        if(target==MAP_FAILED) return 4;
    } else target=(uintptr_t *)mem;
    *target=(uintptr_t)target;
    for(size_t i=n-1;i>0 && !strcmp(order,"random");i--) {
        size_t j=rng(&state)%(i+1),t=positions[i];positions[i]=positions[j];positions[j]=t;
    }
    for(size_t i=0;i<n;i++) {
        uintptr_t *a=(uintptr_t *)(mem+align+positions[i]);
        uintptr_t next=(uintptr_t)(mem+align+positions[(i+1)%n]);
        if(is_spatial) { *a=(uintptr_t)a+offset; *(uintptr_t *)((unsigned char *)a+offset)=next; }
        else *a=next;
    }
    uintptr_t p=(uintptr_t)(mem+align+positions[0]); free(positions);
    for(uint64_t i=0;i<samples;i++) raw[i]=1;
    p=chase(p,n*(is_spatial?4:2)+batch);
    uint64_t m0=mono(),t0=tick_start(); struct timespec pause={0,20000000}; nanosleep(&pause,NULL);
    uint64_t t1=tick_stop(),m1=mono(),freq=0;
#if defined(__aarch64__) && !defined(FALLBACK_TIMER)
    __asm__ volatile("mrs %0, cntfrq_el0" : "=r"(freq));
#endif
    double hz=(double)(t1-t0)*1e9/(m1-m0);
    uint64_t settle=mono(); do {p=chase(p,4096);} while(mono()-settle<100000000ULL);
    helper_state *h=NULL; pthread_t thread;
    if(is_cross) {
        h=aligned_alloc(1024,((sizeof(*h)+1023)/1024)*1024);
        if(!h) return 4;
        memset(h,0,sizeof(*h)); h->p=p; h->loads=offset?batch:0; h->cpu=helper_cpu;
        if(pthread_create(&thread,NULL,helper,h)) return 4;
        while(!atomic_load(&h->ready)) sched_yield();
        if(atomic_load(&h->ready)<0) return 3;
    }
    unsigned long before_huge=huge_kib(mem);
    struct rusage r0,r1; getrusage(RUSAGE_SELF,&r0);
    uint64_t begin=mono();
    for(uint64_t i=0;i<samples;i++) {
        if(is_probe || is_cross || is_hot) {
            sink=chase((uintptr_t)target,32);
            if(is_probe) p=chase(p,batch);
            if(is_cross) {
                atomic_store_explicit(&h->request,(unsigned)i+1,memory_order_release);
                while(atomic_load_explicit(&h->done,memory_order_acquire)!=(unsigned)i+1) {}
            }
        }
        uint64_t a=tick_start();
        if(is_probe || is_cross || is_hot) sink=chase((uintptr_t)target,1);
        else if(!is_empty) p=chase(p,batch);
        raw[i]=tick_stop()-a;
    }
    uint64_t end=mono(); getrusage(RUSAGE_SELF,&r1);
    if(h) {atomic_store(&h->request,UINT32_MAX);pthread_join(thread,NULL);free(h);}
    unsigned long after_huge=huge_kib(mem);
    sink=p;
    FILE *f=fopen(argv[10],"wb");
    if(!f || fwrite(raw,8,samples,f)!=samples || fclose(f)) return 5;
    uint16_t endian=1;
#if defined(FALLBACK_TIMER)
    const char *unit="monotonic_raw_ns";
#elif defined(__x86_64__)
    const char *unit="TSC_ticks";
#else
    const char *unit="CNTVCT_ticks";
#endif
    printf("{\"samples\":%" PRIu64 ",\"batch\":%" PRIu64 ",\"cpu\":%d,\"final_cpu\":%d,\"helper_cpu\":%d,\"unit\":\"%s\",\"counter_frequency\":%" PRIu64 ",\"empirical_ticks_per_second\":%.3f,\"elapsed_ns\":%" PRIu64 ",\"little_endian\":%s,\"major_faults\":%ld,\"minor_faults\":%ld,\"involuntary_switches\":%ld,\"voluntary_switches\":%ld,\"alignment_shift\":%zu,\"page_policy\":\"%s\",\"mapped_bytes\":%zu,\"logical_bytes\":%zu,\"anon_huge_before_kib\":%lu,\"anon_huge_after_kib\":%lu,\"pressure_nodes\":%zu,\"target_in_pressure_mapping\":%s,\"address\":\"%p\",\"target_address\":\"%p\"}\n",
       samples,batch,cpu,sched_getcpu(),is_cross?helper_cpu:-1,unit,freq,hz,end-begin,*(unsigned char *)&endian?"true":"false",
       r1.ru_majflt-r0.ru_majflt,r1.ru_minflt-r0.ru_minflt,r1.ru_nivcsw-r0.ru_nivcsw,r1.ru_nvcsw-r0.ru_nvcsw,
       align,argv[12],mapped,bytes,before_huge,after_huge,n,target_length?"false":"true",(void *)mem,(void *)target);
    free(raw);munmap(mem,mapped);if(target_length)munmap(target,target_length);return 0;
}
