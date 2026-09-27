#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <pthread.h>
#include <sys/socket.h>
#include <netinet/in.h>

volatile int target_health = 100;
volatile int target_score = 1337;
volatile float target_speed = 4.5f;
char target_banner[64] = "PhantomTarget_Active";

int main(int argc, char *argv[]) {
    printf("[TARGET] Started PID: %d\n", getpid());
    printf("[TARGET] Health addr: %p, Score addr: %p, Speed addr: %p\n", 
           (void*)&target_health, (void*)&target_score, (void*)&target_speed);
    fflush(stdout);

    // Create a dummy listening socket for handle/network testing
    int server_fd = socket(AF_INET, SOCK_STREAM, 0);
    if (server_fd >= 0) {
        int opt = 1;
        setsockopt(server_fd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));
        struct sockaddr_in address;
        address.sin_family = AF_INET;
        address.sin_addr.s_addr = INADDR_ANY;
        address.sin_port = htons(19876);
        bind(server_fd, (struct sockaddr*)&address, sizeof(address));
        listen(server_fd, 3);
    }

    int counter = 0;
    while (1) {
        usleep(100000); // 100ms
        counter++;
        if (counter % 50 == 0) {
            // Periodic keepalive / debug message if needed
            // target_health stays 100 unless changed externally
        }
    }

    return 0;
}
