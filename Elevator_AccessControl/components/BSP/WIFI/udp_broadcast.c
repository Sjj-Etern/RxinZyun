#include <string.h>
#include <sys/param.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "lwip/err.h"
#include "lwip/sockets.h"
#include "cJSON.h"
// #include "config.h"
#include "tcp_client.h"
#include "wifi_.h"

static const char *TAG = "UDP";
static int udp_sock = -1;
static struct sockaddr_in dest_addr;
static struct sockaddr_in local_addr;
static char rx_buffer[128];
extern char server_ip[16];   // 声明外部变量，定义在 tcp_client.c 中

// 前置声明接收任务
static void udp_recv_task(void *pvParameters);

void udp_broadcast_start(void)
{
    udp_sock = socket(AF_INET, SOCK_DGRAM, 0);
    if (udp_sock < 0) {
        ESP_LOGE(TAG, "Unable to create socket: errno %d", errno);
        return;
    }

    int broadcast = 1;
    setsockopt(udp_sock, SOL_SOCKET, SO_BROADCAST, &broadcast, sizeof(broadcast));

    local_addr.sin_family = AF_INET;
    local_addr.sin_port = htons(UDP_PORT);
    local_addr.sin_addr.s_addr = htonl(INADDR_ANY);
    if (bind(udp_sock, (struct sockaddr *)&local_addr, sizeof(local_addr)) < 0) {
        ESP_LOGE(TAG, "Socket unable to bind: errno %d", errno);
        close(udp_sock);
        udp_sock = -1;
        return;
    }

    dest_addr.sin_family = AF_INET;
    dest_addr.sin_port = htons(UDP_PORT);
    inet_aton(BROADCAST_ADDR, &dest_addr.sin_addr);

    xTaskCreate(udp_recv_task, "udp_recv", 4096, NULL, 5, NULL); // 任务放在广播里实现
}

static void udp_recv_task(void *pvParameters)
{
    // bool rhost_ok = false;

    while (1) {
        struct sockaddr_in source_addr;
        socklen_t addr_len = sizeof(source_addr);
        int len = recvfrom(udp_sock, rx_buffer, sizeof(rx_buffer)-1, 0,
                           (struct sockaddr *)&source_addr, &addr_len);
        if (len > 0) {
            rx_buffer[len] = 0;
            ESP_LOGI(TAG, "Received UDP: %s", rx_buffer);
            cJSON *root = cJSON_Parse(rx_buffer);
            if (root) {
                cJSON *type = cJSON_GetObjectItem(root, "type");
                if (type && strcmp(type->valuestring, "config") == 0) {
                    cJSON *ip = cJSON_GetObjectItem(root, "ip");
                    cJSON *port = cJSON_GetObjectItem(root, "port");
                    if (ip && port) {
                        strcpy(server_ip, ip->valuestring);
                        tcp_client_set_server(server_ip, port->valueint);
                        // rhost_ok = true;
                        ESP_LOGI(TAG, "Got server: %s:%d\n\n", server_ip, port->valueint);
                    }

                }else{
                    // ESP_LOGI("UDP_RECV_TASK","%s\n",)
                }
                cJSON_Delete(root);
            }
        }else{
            ESP_LOGI("UDP GET","接收数据长度为0");
        }
        // if(rhost_ok) break; // 如果已经获取远端主控机ip，就停止udp侦听任务
    }
    vTaskDelete(NULL);
}

void udp_broadcast_send_discovery(void)
{
    if (udp_sock < 0) return;
    
    // xTaskCreate(udp_recv_task, "udp_recv", 4096, NULL, 5, NULL);
    
    char payload[128];
    snprintf(payload, sizeof(payload), "{\"type\":\"discovery\",\"id\":\"%s\"}", NODE_ID);
    int err = sendto(udp_sock, payload, strlen(payload), 0,
                     (struct sockaddr *)&dest_addr, sizeof(dest_addr));
    if (err < 0) {
        ESP_LOGE(TAG, "Send failed: errno %d", errno);
    } else {
        ESP_LOGI(TAG, "Discovery sent");
    }
}
