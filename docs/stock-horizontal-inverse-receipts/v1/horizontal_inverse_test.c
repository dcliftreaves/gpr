/* Experimental private-kernel oracle and matched in-process benchmark. */
#include "../source/lib/vc5_decoder/inverse.c"
#include <stdio.h>
#include <time.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
STATIC CODEC_ERROR baseline_horizontal(PIXEL *lowpass, PIXEL *highpass, PIXEL *output,
                                              DIMENSION input_width, DIMENSION output_width,
                                              int descale)
{
    const int last_column = input_width - 1;
    
    // Start processing at the beginning of the row
    int column = 0;
    
    int descale_shift = 0;
    
    int32_t even;
    int32_t odd;
    
    /*
     The implementation of the inverse filter includes descaling by a factor of two
     because the last division by two in the computation of the even and odd results
     that is performed using a right arithmetic shift has been omitted from the code.
     */
    if (descale == 2) {
        descale_shift = 1;
    }
    
    // Check that the descaling value is reasonable
    assert(descale_shift >= 0);
    
    // Process the first two output points with special filters for the left border
    even = 0;
    odd = 0;
    
    // Apply the even reconstruction filter to the lowpass band
    even += 11 * lowpass[column + 0];
    even -=  4 * lowpass[column + 1];
    even +=  1 * lowpass[column + 2];
    even += rounding;
    even = DivideByShift(even, 3);
    
    // Add the highpass correction
    even += highpass[column];
    
    // Remove any scaling used during encoding
    even *= (1 << descale_shift);
    
    // The lowpass result should be a positive number
    //assert(0 <= even && even <= INT16_MAX);
    
    // Apply the odd reconstruction filter to the lowpass band
    odd += 5 * lowpass[column + 0];
    odd += 4 * lowpass[column + 1];
    odd -= 1 * lowpass[column + 2];
    odd += rounding;
    odd = DivideByShift(odd, 3);
    
    // Subtract the highpass correction
    odd -= highpass[column];
    
    // Remove any scaling used during encoding
    odd *= (1 << descale_shift);
    
    // The lowpass result should be a positive number
    //assert(0 <= odd && odd <= INT16_MAX);
    
    output[2 * column + 0] = ClampPixel(even);
    output[2 * column + 1] = ClampPixel(odd);
    
    // Advance to the next input column (second pair of output values)
    column++;
    
    // Process the rest of the columns up to the last column in the row
    for (; column < last_column; column++)
    {
        int32_t even = 0;        // Result of convolution with even filter
        int32_t odd = 0;        // Result of convolution with odd filter
        
        // Apply the even reconstruction filter to the lowpass band
        even += lowpass[column - 1];
        even -= lowpass[column + 1];
        even += 4;
        even >>= 3;
        even += lowpass[column + 0];
        
        // Add the highpass correction
        even += highpass[column];
        
        // Remove any scaling used during encoding
        even *= (1 << descale_shift);
        
        // The lowpass result should be a positive number
        //assert(0 <= even && even <= INT16_MAX);
        
        // Place the even result in the even column
        output[2 * column + 0] = ClampPixel(even);
        
        // Apply the odd reconstruction filter to the lowpass band
        odd -= lowpass[column - 1];
        odd += lowpass[column + 1];
        odd += 4;
        odd >>= 3;
        odd += lowpass[column + 0];
        
        // Subtract the highpass correction
        odd -= highpass[column];
        
        // Remove any scaling used during encoding
        odd *= (1 << descale_shift);
        
        // The lowpass result should be a positive number
        //assert(0 <= odd && odd <= INT16_MAX);
        
        // Place the odd result in the odd column
        output[2 * column + 1] = ClampPixel(odd);
    }
    
    // Should have exited the loop at the column for right border processing
    assert(column == last_column);
    
    // Process the last two output points with special filters for the right border
    even = 0;
    odd = 0;
    
    // Apply the even reconstruction filter to the lowpass band
    even += 5 * lowpass[column + 0];
    even += 4 * lowpass[column - 1];
    even -= 1 * lowpass[column - 2];
    even += rounding;
    even = DivideByShift(even, 3);
    
    // Add the highpass correction
    even += highpass[column];
    
    // Remove any scaling used during encoding
    even *= (1 << descale_shift);
    
    // The lowpass result should be a positive number
    //assert(0 <= even && even <= INT16_MAX);
    
    // Place the even result in the even column
    output[2 * column + 0] = ClampPixel(even);
    
    if (2 * column + 1 < output_width)
    {
        // Apply the odd reconstruction filter to the lowpass band
        odd += 11 * lowpass[column + 0];
        odd -=  4 * lowpass[column - 1];
        odd +=  1 * lowpass[column - 2];
        odd += rounding;
        odd = DivideByShift(odd, 3);
        
        // Subtract the highpass correction
        odd -= highpass[column];
        
        // Remove any scaling used during encoding
        odd *= (1 << descale_shift);
        
        // The lowpass result should be a positive number
        //assert(0 <= odd && odd <= INT16_MAX);
        
        // Place the odd result in the odd column
        output[2 * column + 1] = ClampPixel(odd);
    }
    
    return CODEC_ERROR_OKAY;
}
static int floor8(int v) {return v>=0 ? v/8:-((-v+7)/8);}
static int16_t saturate(int v) {return v>32767?32767:v<-32768?-32768:(int16_t)v;}
static void oracle(const int16_t *l,const int16_t *h,int16_t *o,int w,int ow,int descale) {
 for(int x=0;x<w;++x) {
  int e,d;
  if(x==0) {e=floor8(11*l[0]-4*l[1]+l[2]+4);d=floor8(5*l[0]+4*l[1]-l[2]+4);}
  else if(x==w-1) {e=floor8(5*l[x]+4*l[x-1]-l[x-2]+4);d=floor8(11*l[x]-4*l[x-1]+l[x-2]+4);}
  else {e=floor8(l[x-1]-l[x+1]+4)+l[x];d=floor8(-l[x-1]+l[x+1]+4)+l[x];}
  int scale=descale==2?2:1;
  o[2*x]=saturate((e+h[x])*scale);
  if(2*x+1<ow)o[2*x+1]=saturate((d-h[x])*scale);
 }
}
static uint32_t rng=0x8d192a4bu;
static uint32_t next(void) {rng=rng*1664525u+1013904223u;return rng;}
__attribute__((noinline)) static void candidate(int16_t *l,int16_t *h,int16_t *o,int w,int ow,int d) {InvertHorizontalDescale16s(l,h,o,w,ow,d);}
__attribute__((noinline)) static void baseline(int16_t *l,int16_t *h,int16_t *o,int w,int ow,int d) {baseline_horizontal(l,h,o,w,ow,d);}
static double now(void) {struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec+t.tv_nsec*1e-9;}
int main(int argc,char **argv) {
 int16_t low[1056],high[1056],a[2120],b[2120],c[2120],oldlow[1056],oldhigh[1056];
 unsigned long samples=0;
 for(int trial=0;trial<6000;++trial) {
  int w=3+next()%1023,ow=2*w-(trial&1),offset=trial%8,d=(trial&2)?2:0;
  for(int x=0;x<1056;++x) {
   unsigned mode=(trial/4)%7;
   low[x]=mode==0?0:mode==1?32767:mode==2?-32768:mode==3?(x&1?32767:-32768):mode==4?(x%17?0:(int16_t)next()):mode==5?(x*71-32000):(int16_t)next();
   high[x]=(int16_t)next();
  }
  memcpy(oldlow,low,sizeof low);memcpy(oldhigh,high,sizeof high);
  for(int x=0;x<2120;++x)a[x]=b[x]=c[x]=(int16_t)0x5a39;
  oracle(low+offset,high+offset,a+offset,w,ow,d);
  candidate(low+offset,high+offset,b+offset,w,ow,d);
  baseline(low+offset,high+offset,c+offset,w,ow,d);
  if(memcmp(a,b,sizeof a)||memcmp(a,c,sizeof a)||memcmp(low,oldlow,sizeof low)||memcmp(high,oldhigh,sizeof high)) {
   fprintf(stderr,"Mismatch trial=%d width=%d output=%d descale=%d offset=%d\n",trial,w,ow,d,offset);return 2;
  }
  samples+=ow;
 }
 printf("{\"event\":\"oracle\",\"cases\":6000,\"output_samples\":%lu,\"passed\":true}\n",samples);
 if(argc>1 && !strcmp(argv[1],"--bench")) {
  const int w=512,rows=384,passes=400;
  int16_t *l=malloc((size_t)w*rows*2),*h=malloc((size_t)w*rows*2),*out=malloc(w*4);
  if(!l||!h||!out)return 3;
  for(int i=0;i<w*rows;++i){l[i]=(int16_t)next();h[i]=(int16_t)next();}
  const int modes[8]={0,1,1,0,1,0,0,1};
  uint64_t checksum=0;
  for(int run=0;run<8;++run) {
   double start=now();
   for(int pass=0;pass<passes;++pass)for(int row=0;row<rows;++row) {
    if(modes[run])candidate(l+row*w,h+row*w,out,w,2*w,2);
    else baseline(l+row*w,h+row*w,out,w,2*w,2);
    checksum+=(uint16_t)out[(pass+row)%(2*w)];
   }
   printf("{\"event\":\"benchmark\",\"run\":%d,\"candidate\":%s,\"seconds\":%.9f,\"rows\":%d,\"checksum\":%llu}\n",run,modes[run]?"true":"false",now()-start,passes*rows,(unsigned long long)checksum);fflush(stdout);
  }
  free(l);free(h);free(out);
 }
 return 0;
}
