#include <stdio.h>
#include <unistd.h>

__attribute__((constructor))
void on_inject(void) {
    FILE *f = fopen("/tmp/phantom_injected_test.log", "w");
    if (f) {
        fprintf(f, "PhantomSuite Injected Successfully into PID %d\n", getpid());
        fclose(f);
    }
}
