// tcp_client.h
#ifndef TCP_CLIENT_H
#define TCP_CLIENT_H

#include <stdbool.h>

void tcp_client_start(void);
void tcp_client_set_server(const char *ip, int port);
bool tcp_client_is_connected(void);
void tcp_client_send_data(const char *data);

#endif