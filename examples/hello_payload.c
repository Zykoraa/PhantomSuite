#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <time.h>

// Constructor: Executes automatically as soon as dlopen() loads this .so
__attribute__((constructor))
void on_load(void) {
    pid_t pid = getpid();
    time_t now = time(NULL);
    char *time_str = ctime(&now);
    if (time_str) {
        time_str[24] = '\0'; // Strip trailing newline
    }

    FILE *f = fopen("/tmp/phantom_test.log", "a");
    if (f) {
        fprintf(f, "[%s] [+] Hello from PhantomSuite! Payload loaded into PID %d\n", 
                time_str ? time_str : "TIME", pid);
        fclose(f);
    }

    // Optional: Send a desktop notification to Hyprland/Wayland
    char notify_cmd[256];
    snprintf(notify_cmd, sizeof(notify_cmd), 
             "notify-send -a 'PhantomSuite' 'Payload Injected' 'Successfully loaded into PID %d' -t 4000 2>/dev/null", 
             pid);
    system(notify_cmd);
}

// Destructor: Executes automatically when dlclose() unloads this .so
__attribute__((destructor))
void on_unload(void) {
    pid_t pid = getpid();
    FILE *f = fopen("/tmp/phantom_test.log", "a");
    if (f) {
        fprintf(f, "[-] Payload unloaded from PID %d\n", pid);
        fclose(f);
    }

    char notify_cmd[256];
    snprintf(notify_cmd, sizeof(notify_cmd), 
             "notify-send -a 'PhantomSuite' 'Payload Unloaded' 'Module detached from PID %d' -t 3000 2>/dev/null", 
             pid);
    system(notify_cmd);
}
