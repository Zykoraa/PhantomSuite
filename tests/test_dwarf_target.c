#include <stdint.h>
#include <stdbool.h>

typedef struct PlayerData {
    uint32_t player_id;
    float health;
    float max_health;
    char username[32];
    uint8_t flags;
    void* inventory_ptr;
} PlayerData;

typedef struct GameSession {
    uint64_t session_id;
    PlayerData player;
    int32_t score;
    bool is_active;
} GameSession;

int main() {
    PlayerData p = {1, 100.0f, 100.0f, "Eve", 0, 0};
    GameSession s = {1337, p, 9999, true};
    return s.score;
}
