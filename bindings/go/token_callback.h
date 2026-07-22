#ifndef CONTEXTLEASE_GO_TOKEN_CALLBACK_H
#define CONTEXTLEASE_GO_TOKEN_CALLBACK_H
#include "contextlease.h"
extern int32_t contextlease_go_token_count(char* text, void* user_data);
contextlease_token_count_fn contextlease_go_token_count_callback(void);
#endif
