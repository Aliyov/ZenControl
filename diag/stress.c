#define _GNU_SOURCE
#include <immintrin.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <time.h>
#include <sched.h>
static int mode, secs; static double ref; static volatile long errors=0; static size_t memper;
static double now(){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec+t.tv_nsec*1e-9;}
static double fma_block(){
  __m256d a[8],m=_mm256_set1_pd(0.999999999),c=_mm256_set1_pd(1e-9);
  for(int i=0;i<8;i++)a[i]=_mm256_set1_pd(1.0+i*1e-3);
  for(long n=0;n<4000000;n++) for(int i=0;i<8;i++) a[i]=_mm256_fmadd_pd(a[i],m,c);
  double s=0,o[4]; for(int i=0;i<8;i++){_mm256_storeu_pd(o,a[i]);s+=o[0]+o[1]+o[2]+o[3];} return s;}
static void* worker(void*arg){
  long id=(long)arg; cpu_set_t cs; CPU_ZERO(&cs); CPU_SET(id,&cs); pthread_setaffinity_np(pthread_self(),sizeof cs,&cs);
  double end=now()+secs; long iters=0;
  if(mode==0){ while(now()<end){ double r=fma_block(); iters++; if(r!=ref){__sync_fetch_and_add(&errors,1); fprintf(stderr,"FMA MISMATCH cpu%ld %.17g vs %.17g\n",id,r,ref);} } }
  else { uint64_t*b=malloc(memper); size_t n=memper/8; uint64_t pass=0;
    while(now()<end){ uint64_t k=0x9E3779B97F4A7C15ULL*(pass+1+id);
      for(size_t i=0;i<n;i++) b[i]=(i*k)^(k>>7);
      for(size_t i=0;i<n;i++) if(b[i]!=((i*k)^(k>>7))){__sync_fetch_and_add(&errors,1); if(errors<20) fprintf(stderr,"MEM MISMATCH cpu%ld idx %zu\n",id,i);}
      pass++; iters++; } free(b); }
  return (void*)iters; }
int main(int c,char**v){ mode=strcmp(v[1],"fma")?1:0; secs=atoi(v[2]); int nt=atoi(v[3]); memper=(c>4?atol(v[4]):64)<<20;
  ref=fma_block(); pthread_t t[64]; for(long i=0;i<nt;i++) pthread_create(&t[i],0,worker,(void*)i);
  long tot=0; for(int i=0;i<nt;i++){void*r; pthread_join(t[i],&r); tot+=(long)r;}
  printf("mode=%s threads=%d iters=%ld errors=%ld\n",v[1],nt,tot,errors); return errors?1:0; }
