#define _GNU_SOURCE
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <sys/mman.h>
#include <unistd.h>
typedef void (*kernel_fn)(const uint16_t*,const uint16_t*,const uint16_t*,int16_t*,unsigned,unsigned);
extern void baseline_unpack14_channel(const uint16_t*,const uint16_t*,const uint16_t*,int16_t*,unsigned,unsigned);
extern void wide_unpack14_channel(const uint16_t*,const uint16_t*,const uint16_t*,int16_t*,unsigned,unsigned);
extern uint16_t EncoderLogCurve[];
extern void SetupEncoderLogCurve(void);
static kernel_fn kernels[]={baseline_unpack14_channel,wide_unpack14_channel};
static uint64_t checks;
static void die(const char *s){fprintf(stderr,"%s\n",s);exit(1);}
static double now(void){struct timespec t;if(clock_gettime(CLOCK_MONOTONIC,&t))die("clock");return t.tv_sec+t.tv_nsec*1e-9;}
static void check(const uint16_t *a,const uint16_t *b,int16_t *out,unsigned width,unsigned channel){
 for(unsigned kind=0;kind<2;kind++){
  kernels[kind](a,b,EncoderLogCurve,out,width,channel);
  for(unsigned x=0;x<width;x++){
   int g1=EncoderLogCurve[a[2*x+1]>>2],g2=EncoderLogCurve[b[2*x]>>2],gs=(g1+g2)/2;
   int wanted=channel==0?gs:channel==3?(g1-g2+4096)/2:(EncoderLogCurve[(channel==1?a[2*x]:b[2*x+1])>>2]+4096-gs)/2;
   if(out[x]!=wanted)die("scalar/assembly disagreement");
  }
  checks++;
 }
}
static uint16_t *load(const char *path,size_t bytes){
 FILE *f=fopen(path,"rb");if(!f)die("input open");void *p=0;
 if(posix_memalign(&p,64,bytes))die("alloc");
 if(fread(p,1,bytes,f)!=bytes||fgetc(f)!=EOF)die("input size");fclose(f);
 for(size_t i=0;i<bytes/2;i++)if(((uint16_t*)p)[i]>16383)die("count domain");return p;
}
int main(int argc,char **argv){
 if(argc!=4)die("usage: kernel repeats raw0 raw1");unsigned repeats=strtoul(argv[1],0,10);if(!repeats||repeats>1000)die("repeats");
 SetupEncoderLogCurve();uint16_t a[288],b[288];int16_t out[160];
 for(unsigned i=0;i<288;i++){a[i]=(i*1327+3)&16383;b[i]=(i*831+16380)&16383;}
 for(unsigned offset=0;offset<8;offset++)for(unsigned width=4;width<=132;width+=4)for(unsigned c=0;c<4;c++){
  memset(out,0x5a,sizeof(out));check(a+offset,b+7-offset,out+offset,width,c);
  for(unsigned x=0;x<offset;x++)if(out[x]!=0x5a5a)die("prefix overwritten");
  for(unsigned x=offset+width;x<160;x++)if(out[x]!=0x5a5a)die("suffix overwritten");
 }
 for(unsigned k=0;k<2;k++)kernels[k](NULL,NULL,NULL,NULL,0,0);
 long page=sysconf(_SC_PAGESIZE);if(page<16384&&page<4096)die("page");
 void *maps[3];for(unsigned i=0;i<3;i++){
  maps[i]=mmap(NULL,page*3,PROT_NONE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);if(maps[i]==MAP_FAILED)die("mmap");
  if(mprotect((char*)maps[i]+page,page,PROT_READ|PROT_WRITE))die("mprotect");
 }
 for(unsigned width=4;width<=512;width+=4){
  uint16_t *r0=(uint16_t*)((char*)maps[0]+2*page-width*4),*r1=(uint16_t*)((char*)maps[1]+2*page-width*4);
  int16_t *dst=(int16_t*)((char*)maps[2]+2*page-width*2);
  for(unsigned i=0;i<width*2;i++){r0[i]=(i*317+2)&16383;r1[i]=(i*173+1)&16383;}
  for(unsigned c=0;c<4;c++)check(r0,r1,dst,width,c);
 }
 for(unsigned i=0;i<3;i++)munmap(maps[i],page*3);
 enum{W=4096,H=3072};uint16_t *images[2]={load(argv[2],W*H*2),load(argv[3],W*H*2)};
 int16_t *result=malloc(W);if(!result)die("alloc");
 for(unsigned s=0;s<2;s++)for(unsigned c=0;c<4;c++)for(unsigned y=0;y<H;y+=2)
  check(images[s]+y*W,images[s]+(y+1)*W,result,W/2,c);
 printf("{\"scalar_comparisons\":%llu,\"guard_pages\":true,\"row_offset_cases\":true,\"runs\":[",(unsigned long long)checks);
 int order[]={0,1,1,0,1,0,0,1};
 for(unsigned r=0;r<8;r++){
  unsigned kind=order[r];double begin=now();
  for(unsigned i=0;i<repeats;i++)for(unsigned s=0;s<2;s++)for(unsigned c=0;c<4;c++)for(unsigned y=0;y<H;y+=2)
   kernels[kind](images[s]+y*W,images[s]+(y+1)*W,EncoderLogCurve,result,W/2,c);
  double elapsed=now()-begin;uint64_t sum=0;for(unsigned i=0;i<W/2;i++)sum=sum*131+(uint16_t)result[i];
  printf("%s{\"kind\":\"%s\",\"frames\":%u,\"elapsed_s\":%.9f,\"ms_per_frame\":%.9f,\"last_row_hash\":\"%016llx\"}",r?",":"",kind?"wide":"baseline",repeats*2,elapsed,elapsed*1000/(repeats*2),(unsigned long long)sum);fflush(stdout);
 }
 printf("]}\n");free(result);free(images[0]);free(images[1]);return 0;
}
