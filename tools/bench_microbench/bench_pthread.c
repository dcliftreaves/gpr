/* Measure pthread_create + pthread_join overhead on Pi 5.
   If decoder creates 12 threads per call, what's the cost? */
#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdlib.h>
#include <pthread.h>
#include <time.h>

static void *empty_runner(void *arg) { (void)arg; return NULL; }

static double now_sec(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec + ts.tv_nsec * 1e-9;
}

int main(void) {
    const int batches = 1000;
    const int threads_per = 12;  /* matches decoder pattern: 4+4+4 */
    pthread_t th[12];

    double t0 = now_sec();
    for (int b = 0; b < batches; b++) {
        for (int i = 0; i < threads_per; i++)
            pthread_create(&th[i], NULL, empty_runner, NULL);
        for (int i = 0; i < threads_per; i++)
            pthread_join(th[i], NULL);
    }
    double dt = now_sec() - t0;

    printf("Per-batch (%d threads create+join): %.3f ms\n",
           threads_per, dt * 1000.0 / batches);
    printf("Per-thread create+join: %.3f us\n",
           dt * 1e6 / batches / threads_per);
    return 0;
}
