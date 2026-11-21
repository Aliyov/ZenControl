#include <stdio.h>
#include <stdlib.h>
#include <time.h>
typedef int CUresult; typedef int CUdevice; typedef void *CUcontext, *CUmodule, *CUfunction; typedef unsigned long long CUdeviceptr;
CUresult cuInit(unsigned); CUresult cuDeviceGet(CUdevice*, int); CUresult cuCtxCreate_v2(CUcontext*, unsigned, CUdevice);
CUresult cuModuleLoadData(CUmodule*, const void*); CUresult cuModuleGetFunction(CUfunction*, CUmodule, const char*);
CUresult cuMemAlloc_v2(CUdeviceptr*, size_t); CUresult cuCtxSynchronize(void);
CUresult cuLaunchKernel(CUfunction, unsigned, unsigned, unsigned, unsigned, unsigned, unsigned, unsigned, void*, void**, void**);
static const char *ptx =
".version 6.0\n.target sm_52\n.address_size 64\n"
".visible .entry burn(.param .u64 o, .param .u32 n){\n"
".reg .pred %p<2>; .reg .f32 %f<12>; .reg .b32 %r<8>; .reg .b64 %rd<4>;\n"
"ld.param.u64 %rd1,[o]; ld.param.u32 %r1,[n];\n"
"mov.u32 %r2,%tid.x; mov.u32 %r3,%ctaid.x; mov.u32 %r4,%ntid.x; mad.lo.s32 %r5,%r3,%r4,%r2;\n"
"cvt.rn.f32.u32 %f1,%r5; mov.f32 %f3,0f3F7FFFFF; mov.f32 %f4,0f33D6BF95;\n"
"mov.f32 %f5,%f1; mov.f32 %f6,0f3F800000; mov.f32 %f7,%f1; mov.f32 %f8,0f40000000; mov.u32 %r6,0;\n"
"L: fma.rn.f32 %f5,%f5,%f3,%f4; fma.rn.f32 %f6,%f6,%f3,%f4; fma.rn.f32 %f7,%f7,%f3,%f4; fma.rn.f32 %f8,%f8,%f3,%f4;\n"
"fma.rn.f32 %f5,%f5,%f3,%f4; fma.rn.f32 %f6,%f6,%f3,%f4; fma.rn.f32 %f7,%f7,%f3,%f4; fma.rn.f32 %f8,%f8,%f3,%f4;\n"
"add.u32 %r6,%r6,1; setp.lt.u32 %p1,%r6,%r1; @%p1 bra L;\n"
"add.f32 %f9,%f5,%f6; add.f32 %f9,%f9,%f7; add.f32 %f9,%f9,%f8;\n"
"cvta.to.global.u64 %rd2,%rd1; mul.wide.u32 %rd3,%r5,4; add.u64 %rd2,%rd2,%rd3; st.global.f32 [%rd2],%f9; ret; }\n";
static int gpu_temp(void){ FILE *p=popen("nvidia-smi --query-gpu=temperature.gpu --format=csv,noheader,nounits","r"); int t=0; if(p){if(fscanf(p,"%d",&t)!=1)t=0; pclose(p);} return t; }
int main(int c, char **v){
  int secs = c>1 ? atoi(v[1]) : 20; CUdevice d; CUcontext ctx; CUmodule m; CUfunction f; CUdeviceptr out;
  if (cuInit(0) || cuDeviceGet(&d,0) || cuCtxCreate_v2(&ctx,0,d)) { fprintf(stderr,"cuda init failed\n"); return 1; }
  int e = cuModuleLoadData(&m, ptx); if (e) { fprintf(stderr,"ptx load failed %d\n", e); return 1; }
  cuModuleGetFunction(&f, m, "burn");
  unsigned blocks=4096, threads=256, n=20000; cuMemAlloc_v2(&out, (size_t)blocks*threads*4);
  void *args[] = {&out, &n}; time_t end = time(0)+secs, chk = 0; long launches = 0;
  struct timespec a, b; clock_gettime(CLOCK_MONOTONIC, &a);
  while (time(0) < end) {
    cuLaunchKernel(f, blocks,1,1, threads,1,1, 0, 0, args, 0); cuCtxSynchronize(); launches++;
    if (time(0) != chk) { chk = time(0); if (gpu_temp() >= 87) { printf("ABORT: GPU 87C\n"); return 2; } }
  }
  clock_gettime(CLOCK_MONOTONIC, &b);
  double t = (b.tv_sec - a.tv_sec) + (b.tv_nsec - a.tv_nsec) * 1e-9;
  printf("GFLOPS %.1f\n", (double)launches * blocks * threads * n * 16 / t / 1e9);
  return 0;
}
