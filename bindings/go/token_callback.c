#include "token_callback.h"
static int32_t contextlease_go_token_count_bridge(const char* text, void* user_data) {
    return contextlease_go_token_count((char*)text, user_data);
}
contextlease_token_count_fn contextlease_go_token_count_callback(void) {
    return contextlease_go_token_count_bridge;
}
