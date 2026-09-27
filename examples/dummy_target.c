#include <stdio.h>
#include <unistd.h>

int main(void) {
    printf("[*] Dummy target started. PID: %d\n", getpid());
    printf("[*] Waiting for injection. Press Ctrl+C to exit.\n");
    fflush(stdout);

    int count = 0;
    while (1) {
        sleep(1);
        count++;
        if (count % 10 == 0) {
            printf("[PID %d] Heartbeat (running for %d seconds)...\n", getpid(), count);
            fflush(stdout);
        }
    }
    return 0;
}
