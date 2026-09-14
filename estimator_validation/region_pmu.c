/* Phase-II-only preload observer. The frozen estimator binary is unchanged.
 * Its two getrusage calls bracket exactly the timed sampling loop. Count user
 * events only; initialization, warm-up and output are outside this region.
 * Counts include timing/loop/stack traffic, not just the pointer-chain loads. */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <inttypes.h>
#include <linux/perf_event.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/resource.h>
#include <sys/syscall.h>
#include <unistd.h>
static int calls, leader=-1, member=-1, saved_error;
static uint64_t counts[5];
static long bytes_read=-1;
static int (*original)(__rusage_who_t,struct rusage *);
static int open_counter(uint64_t config,int group) {
 struct perf_event_attr a; memset(&a,0,sizeof(a));
 a.type=PERF_TYPE_HW_CACHE;a.size=sizeof(a);a.config=config;
 a.disabled=(group==-1);a.exclude_kernel=1;a.exclude_hv=1;
 a.read_format=PERF_FORMAT_GROUP|PERF_FORMAT_TOTAL_TIME_ENABLED|PERF_FORMAT_TOTAL_TIME_RUNNING;
 return (int)syscall(SYS_perf_event_open,&a,0,-1,group,0);
}
int getrusage(__rusage_who_t who,struct rusage *usage) {
 if(!original) original=dlsym(RTLD_NEXT,"getrusage");
 if(!original) _exit(90);
 if(who!=RUSAGE_SELF) return original(who,usage);
 ++calls;
 if(calls==1) {
  const char *level=getenv("VALIDATION_LEVEL");
  uint64_t cache=level && !strcmp(level,"LL")?PERF_COUNT_HW_CACHE_LL:PERF_COUNT_HW_CACHE_L1D;
  leader=open_counter(cache,-1);
  if(leader<0) saved_error=errno;
  else {member=open_counter(cache|(1ULL<<16),leader);if(member<0)saved_error=errno;}
  int rc=original(who,usage);
  if(!saved_error && (ioctl(leader,PERF_EVENT_IOC_RESET,PERF_IOC_FLAG_GROUP)<0 || ioctl(leader,PERF_EVENT_IOC_ENABLE,PERF_IOC_FLAG_GROUP)<0))saved_error=errno;
  return rc;
 }
 if(calls==2 && !saved_error) {
  if(ioctl(leader,PERF_EVENT_IOC_DISABLE,PERF_IOC_FLAG_GROUP)<0)saved_error=errno;
  bytes_read=read(leader,counts,sizeof(counts));if(bytes_read<0)saved_error=errno;
 }
 return original(who,usage);
}
__attribute__((destructor)) static void finish(void) {
 const char *path=getenv("VALIDATION_OUTPUT");if(!path)return;
 FILE *f=fopen(path,"w");if(!f)return;
 fprintf(f,"{\"calls\":%d,\"errno\":%d,\"read_bytes\":%ld,\"nr\":%"PRIu64",\"enabled_ns\":%"PRIu64",\"running_ns\":%"PRIu64",\"accesses\":%"PRIu64",\"misses\":%"PRIu64"}\n",calls,saved_error,bytes_read,counts[0],counts[1],counts[2],counts[3],counts[4]);
 fclose(f);if(member>=0)close(member);if(leader>=0)close(leader);
}
