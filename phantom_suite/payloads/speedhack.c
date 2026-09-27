#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <time.h>
#include <sys/time.h>
#include <dlfcn.h>
#include <fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>

struct speedhack_data {
    volatile double speed;
    volatile int enabled;
};

static int (*real_clock_gettime)(clockid_t, struct timespec *) = NULL;
static int (*real_gettimeofday)(struct timeval *, void *) = NULL;

static struct speedhack_data *shm_ptr = NULL;
static int shm_fd = -1;

// Monotonic time tracking
static struct timespec last_real_mono = {0, 0};
static struct timespec virtual_mono = {0, 0};

// Realtime tracking
static struct timespec last_real_rt = {0, 0};
static struct timespec virtual_rt = {0, 0};

static void init_shm(void) {
    char shm_name[64];
    snprintf(shm_name, sizeof(shm_name), "/phantom_speed_%d", getpid());

    shm_fd = shm_open(shm_name, O_CREAT | O_RDWR, 0666);
    if (shm_fd >= 0) {
        ftruncate(shm_fd, sizeof(struct speedhack_data));
        shm_ptr = (struct speedhack_data *)mmap(
            NULL, sizeof(struct speedhack_data),
            PROT_READ | PROT_WRITE, MAP_SHARED, shm_fd, 0
        );
        if (shm_ptr != MAP_FAILED && shm_ptr != NULL) {
            shm_ptr->speed = 1.0;
            shm_ptr->enabled = 1;
        } else {
            shm_ptr = NULL;
        }
    }
}

__attribute__((constructor))
void speedhack_init(void) {
    real_clock_gettime = dlsym(RTLD_NEXT, "clock_gettime");
    real_gettimeofday = dlsym(RTLD_NEXT, "gettimeofday");

    init_shm();

    if (real_clock_gettime) {
        real_clock_gettime(CLOCK_MONOTONIC, &last_real_mono);
        virtual_mono = last_real_mono;

        real_clock_gettime(CLOCK_REALTIME, &last_real_rt);
        virtual_rt = last_real_rt;
    }
}

__attribute__((destructor))
void speedhack_cleanup(void) {
    if (shm_ptr) {
        munmap(shm_ptr, sizeof(struct speedhack_data));
        shm_ptr = NULL;
    }
    if (shm_fd >= 0) {
        close(shm_fd);
        shm_fd = -1;
    }
    char shm_name[64];
    snprintf(shm_name, sizeof(shm_name), "/phantom_speed_%d", getpid());
    shm_unlink(shm_name);
}

int clock_gettime(clockid_t clk_id, struct timespec *tp) {
    if (!real_clock_gettime) {
        real_clock_gettime = dlsym(RTLD_NEXT, "clock_gettime");
        if (!real_clock_gettime) {
            return -1;
        }
    }

    if (!shm_ptr || !shm_ptr->enabled) {
        return real_clock_gettime(clk_id, tp);
    }

    double speed = shm_ptr->speed;
    if (speed <= 0.001) speed = 0.001;
    if (speed > 100.0) speed = 100.0;

    struct timespec now;
    int res = real_clock_gettime(clk_id, &now);
    if (res != 0 || !tp) {
        return res;
    }

    if (clk_id == CLOCK_MONOTONIC || clk_id == CLOCK_MONOTONIC_RAW) {
        double delta_sec = (now.tv_sec - last_real_mono.tv_sec) + 
                           (now.tv_nsec - last_real_mono.tv_nsec) * 1e-9;
        if (delta_sec < 0) delta_sec = 0;

        last_real_mono = now;

        double v_delta_sec = delta_sec * speed;
        virtual_mono.tv_sec += (time_t)v_delta_sec;
        virtual_mono.tv_nsec += (long)((v_delta_sec - (time_t)v_delta_sec) * 1e9);

        if (virtual_mono.tv_nsec >= 1000000000L) {
            virtual_mono.tv_sec += virtual_mono.tv_nsec / 1000000000L;
            virtual_mono.tv_nsec %= 1000000000L;
        }

        *tp = virtual_mono;
        return 0;
    } else if (clk_id == CLOCK_REALTIME) {
        double delta_sec = (now.tv_sec - last_real_rt.tv_sec) + 
                           (now.tv_nsec - last_real_rt.tv_nsec) * 1e-9;
        if (delta_sec < 0) delta_sec = 0;

        last_real_rt = now;

        double v_delta_sec = delta_sec * speed;
        virtual_rt.tv_sec += (time_t)v_delta_sec;
        virtual_rt.tv_nsec += (long)((v_delta_sec - (time_t)v_delta_sec) * 1e9);

        if (virtual_rt.tv_nsec >= 1000000000L) {
            virtual_rt.tv_sec += virtual_rt.tv_nsec / 1000000000L;
            virtual_rt.tv_nsec %= 1000000000L;
        }

        *tp = virtual_rt;
        return 0;
    }

    return real_clock_gettime(clk_id, tp);
}

int gettimeofday(struct timeval *tv, void *tz) {
    if (!tv) {
        return 0;
    }
    struct timespec ts;
    int res = clock_gettime(CLOCK_REALTIME, &ts);
    if (res == 0) {
        tv->tv_sec = ts.tv_sec;
        tv->tv_usec = ts.tv_nsec / 1000;
        return 0;
    }

    if (!real_gettimeofday) {
        real_gettimeofday = dlsym(RTLD_NEXT, "gettimeofday");
    }
    return real_gettimeofday ? real_gettimeofday(tv, tz) : -1;
}
