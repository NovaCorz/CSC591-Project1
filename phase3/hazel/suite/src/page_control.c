#define _GNU_SOURCE
#include <stdint.h>
#include <errno.h>
#include <sys/resource.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

/* Supplemental Phase-I translation control. It includes the unchanged primary
 * program and replaces ONLY its first anonymous allocation/advice/unmap path.
 * Read OS page-backing metadata, never CPU cache geometry or counters. */
static void *control_mem;
static size_t control_length, control_logical_bytes, control_pmd;
static const char *control_raw;
static int control_advice_rc=-2;
static int control_first_mapping=1;
static unsigned long control_huge_before_kib, control_huge_after_kib;
static int control_usage_reads;

static size_t pmd_page_size(void) {
    FILE *f=fopen("/sys/kernel/mm/transparent_hugepage/hpage_pmd_size","r");
    unsigned long n=0;
    if(f) { if(fscanf(f,"%lu",&n)!=1) n=0; fclose(f); }
    return (size_t)n;
}
static void *control_mmap(void *address,size_t length,int prot,int flags,int fd,off_t offset) {
    if(!control_first_mapping) return mmap(address,length,prot,flags,fd,offset);
    control_first_mapping=0; control_logical_bytes=length; control_pmd=pmd_page_size();
    if(!control_pmd || (control_pmd&(control_pmd-1)) || control_pmd>67108864) {
        fprintf(stderr,"THP control unavailable: missing/unsupported PMD page size (resource limit 64 MiB)\n");
        errno=ENOTSUP; return MAP_FAILED;
    }
    control_length=(length+control_pmd-1)/control_pmd*control_pmd;
    size_t reserve=control_length+control_pmd;
    void *raw=mmap(address,reserve,prot,flags,fd,offset);
    if(raw==MAP_FAILED) return raw;
    uintptr_t base=(uintptr_t)raw;
    uintptr_t aligned=(base+control_pmd-1)&~(uintptr_t)(control_pmd-1);
    size_t prefix=aligned-base, suffix=reserve-prefix-control_length;
    if(prefix) munmap(raw,prefix);
    if(suffix) munmap((void *)(aligned+control_length),suffix);
    control_mem=(void *)aligned;
    return control_mem;
}
static int control_madvise(void *address,size_t length,int advice) {
    if(address==control_mem) {
        control_advice_rc=madvise(address,control_length,MADV_HUGEPAGE);
        return control_advice_rc;
    }
    return madvise(address,length,advice);
}
static unsigned long current_huge_kib(void) {
    FILE *f=fopen("/proc/self/smaps","r");
    char line[512]; int matched=0; unsigned long huge=0;
    if(!f) return 0;
    while(fgets(line,sizeof(line),f)) {
        unsigned long start,end,value;
        if(sscanf(line,"%lx-%lx",&start,&end)==2) {
            if(matched) break;
            matched=(uintptr_t)control_mem>=start && (uintptr_t)control_mem<end;
        } else if(matched && sscanf(line,"AnonHugePages: %lu kB",&value)==1) huge=value;
    }
    fclose(f); return huge;
}
static int control_getrusage(int who, struct rusage *usage) {
    if(control_usage_reads++==0) {
        control_huge_before_kib=current_huge_kib();
        return getrusage(who,usage);
    }
    int rc=getrusage(who,usage);
    control_huge_after_kib=current_huge_kib();
    return rc;
}
static void save_page_metadata(void) {
    unsigned long kernel_kib=0,mmu_kib=0,huge_kib=0;
    int matched=0;
    FILE *f=fopen("/proc/self/smaps","r");
    char line[512];
    if(f) {
        while(fgets(line,sizeof(line),f)) {
            unsigned long start,end,value;
            if(sscanf(line,"%lx-%lx",&start,&end)==2) {
                if(matched) break;
                matched=(uintptr_t)control_mem>=start && (uintptr_t)control_mem<end;
            } else if(matched) {
                if(sscanf(line,"KernelPageSize: %lu kB",&value)==1) kernel_kib=value;
                if(sscanf(line,"MMUPageSize: %lu kB",&value)==1) mmu_kib=value;
                if(sscanf(line,"AnonHugePages: %lu kB",&value)==1) huge_kib=value;
            }
        }
        fclose(f);
    }
    size_t len=strlen(control_raw)+32;
    char *path=malloc(len);
    if(!path) return;
    snprintf(path,len,"%s.pages.json",control_raw);
    f=fopen(path,"w");
    if(f) {
        fprintf(f,"{\"policy\":\"MADV_HUGEPAGE for this allocation only\",\"logical_bytes\":%zu,\"mapped_bytes\":%zu,\"pmd_page_bytes\":%zu,\"advice_rc\":%d,\"mapping_found\":%s,\"kernel_page_kib\":%lu,\"mmu_page_kib\":%lu,\"anon_huge_kib\":%lu,\"anon_huge_before_kib\":%lu,\"anon_huge_after_kib\":%lu,\"note\":\"Primary stdout field madvise_nohugepage_rc is the return code of this HUGEPAGE hook in this separate control binary\"}\n",control_logical_bytes,control_length,control_pmd,control_advice_rc,matched?"true":"false",kernel_kib,mmu_kib,huge_kib,control_huge_before_kib,control_huge_after_kib);
        fclose(f);
    }
    free(path);
}
static int control_munmap(void *address,size_t length) {
    if(address==control_mem) { save_page_metadata(); return munmap(address,control_length); }
    return munmap(address,length);
}
#define mmap control_mmap
#define madvise control_madvise
#define munmap control_munmap
#define getrusage control_getrusage
#define main primary_benchmark_main
#include "cache_bench.c"
#undef mmap
#undef madvise
#undef munmap
#undef main
#undef getrusage
int main(int argc,char **argv) {
    if(argc!=11) { fprintf(stderr,"Page control uses the primary benchmark arguments\n"); return 2; }
    control_raw=argv[10];
    return primary_benchmark_main(argc,argv);
}
