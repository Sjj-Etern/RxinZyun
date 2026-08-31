#include <string.h>
#include <sys/socket.h>
#include <netdb.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "cJSON.h"
#include <lwip/sockets.h>
#include <arpa/inet.h>  // 必须加
#include "nvs_flash.h"
#include "nvs.h"

#include "tcp_client.h"
#include "wifi_.h"
#include "relay.h"
#include "emission.h"
#include "dht11.h"

// #include "../../../main/main.h"

static const char *TAG = "TCP_CLIENT";
static int tcp_sock = -1;
char server_ip[16] = {0};          // ✅ 定义全局变量（关键）
static int server_port = TCP_PORT;
static bool connected = false;
static TaskHandle_t tcp_task_handle = NULL;

// 前置声明任务函数
static void tcp_client_task(void *pvParameters);



// 你在 send 之前/之后，都可以调用这个函数
void get_remote_info(int sock) {
    struct sockaddr_in addr;
    socklen_t addr_len = sizeof(addr);

    // ✅ 获取远端 IP 和端口
    if (getpeername(sock, (struct sockaddr*)&addr, &addr_len) == 0) {
        // 远端 IP
        char ip[INET_ADDRSTRLEN];
        inet_ntop(AF_INET, &addr.sin_addr, ip, INET_ADDRSTRLEN);

        // 远端端口
        uint16_t port = ntohs(addr.sin_port);

        printf("远端地址：%s:%d\n", ip, port);
    } else {
        printf("获取失败\n");
    }
}

void tcp_client_start(void)        // ✅ 实现此函数（main.c 中调用）
{
    if (tcp_task_handle == NULL) {
        xTaskCreate(tcp_client_task, "tcp_client", 8192, NULL, 5, &tcp_task_handle);
        ESP_LOGI(TAG, "TCP client task started");
    }
}

void tcp_client_send_data(const char *data)
{
    if (tcp_sock >= 0 && connected) {
        
        get_remote_info(tcp_sock);  // 获取远端ip和端口

        int ret = send(tcp_sock, data, strlen(data), 0);
        if (ret < 0) {
            ESP_LOGE(TAG, "Send failed: errno %d", errno);
        }else{
            ESP_LOGI(TAG,"TCP Send OK, sended %d words",ret);
        }
    } else {
        ESP_LOGW(TAG, "Cannot send, not connected");
    }
}

void tcp_client_set_server(const char *ip, int port)
{
    strcpy(server_ip, ip);
    server_port = port;
    ESP_LOGI(TAG, "Server set to %s:%d", server_ip, server_port);
}

bool tcp_client_is_connected(void)
{
    // 未创建socket或已关闭，直接返回未连接，避免对无效fd探测误报"connection broken"
    if (tcp_sock < 0) {
        connected = false;
        return false;
    }

    //  动态检测
    // 尝试读取0字节，探测连接状态
    char dummy;
    ssize_t rec = recv(tcp_sock, &dummy, 0, MSG_DONTWAIT);

    if (rec < 0) {
        // EAGAIN 表示正常，无数据；其他错误=断开
        if (errno == EAGAIN || errno == EWOULDBLOCK) {
            connected = true;
            // return true;
        } else {
            ESP_LOGW(TAG, "connection broken by error");
            close(tcp_sock);
            tcp_sock = -1;
            connected=false;            
        }
    } else if (rec == 0) {
        // 对端关闭连接
        ESP_LOGW(TAG, "connection closed by peer");
        close(tcp_sock);
        tcp_sock = -1;
        connected = false;
    }
    
    return connected;

}

/**
 * 收到主控机发来的命令后，回馈当前状态
 */
void echo_cmd(sensor_data_t tmpdata){   
    char buf[512];
    sprintf(buf,"{\"nodeid\":\"%s\",\"temp\":%4.1f,\"humi\":%.1f,\"lux\":%.1f,\"press\":%.0f,\"water\":%.0f,\"co\":%.0f,\"ch4\":%.0f,\"voc\":%.0f,\"pm10\":%.0f, \"auto\":%d,\"relay1_lighting\":%d,\"relay2_ventilate\":%d,\"relay3_dehumidify\":%d}",
            NODE_ID,
            tmpdata.temp,
            tmpdata.humi,
            tmpdata.light,
            tmpdata.pressure,
            tmpdata.water,
            tmpdata.co,
            tmpdata.ch4,
            tmpdata.voc,
            tmpdata.pm10,
            tmpdata.auto_opt,
            
            tmpdata.relay1_lighting,
            tmpdata.relay2_ventilate,
            tmpdata.relay3_dehumidify 
            );
    // ESP_LOGI("ENV_WATCH_THREAD","SEND buf length:%d",sizeof(buf));
    tcp_client_send_data(buf);
}

static void tcp_client_task(void *pvParameters)
{
    while (1) {
        if (server_ip[0] == 0) {
            vTaskDelay(pdMS_TO_TICKS(1000));
            ESP_LOGI("TCP_CLIENT_TASK","server_ip[0]=0");
            continue;
        }

        tcp_sock = socket(AF_INET, SOCK_STREAM, 0);
        if (tcp_sock < 0) {
            ESP_LOGE(TAG, "Socket create error");
            vTaskDelay(pdMS_TO_TICKS(5000));
            continue;
        }

        struct sockaddr_in dest_addr;
        dest_addr.sin_family = AF_INET;
        dest_addr.sin_port = htons(server_port);
        inet_pton(AF_INET, server_ip, &dest_addr.sin_addr);

        ESP_LOGI(TAG, "Now connect to %s:%d", server_ip, server_port);
        int err = connect(tcp_sock, (struct sockaddr *)&dest_addr, sizeof(dest_addr));
        if (err != 0) {
            // errno含义: 104=连接被重置(后端10833未监听/后端未启动) 111=拒绝连接 113=主机不可达 110=连接超时
            ESP_LOGE(TAG, "Connect failed, errno=%d (104=后端未启动/10833未监听, 113=网络不可达, 110=超时)", errno);
            close(tcp_sock);
            tcp_sock = -1;
            vTaskDelay(pdMS_TO_TICKS(5000));
            continue;
        }

        connected = true;
        ESP_LOGI(TAG, "[TCP] 已连接到后端服务端");
        // sensor_data_t data={0};
        char rx_buffer[256];

        while (1) {

            int len = recv(tcp_sock, rx_buffer, sizeof(rx_buffer)-1, 0);
            if (len <= 0) {
                ESP_LOGW(TAG, "[TCP] 连接断开，准备重连...");
                connected = false;
                close(tcp_sock);
                tcp_sock = -1;
                break;
            }            

            rx_buffer[len] = 0;
            ESP_LOGI(TAG, "[RECV] %s", rx_buffer);

            /* ===== 电梯命令解析（JSON格式，与后端 elevator_control.py 对接）===== */
            cJSON *root = cJSON_Parse(rx_buffer);
            if (root != NULL) {
                cJSON *cmd_item = cJSON_GetObjectItem(root, "cmd");
                cJSON *seq_item = cJSON_GetObjectItem(root, "seq");
                int seq = (seq_item != NULL && cJSON_IsNumber(seq_item)) ? seq_item->valueint : 0;

                if (cmd_item != NULL && cJSON_IsString(cmd_item)) {
                    const char *cmd = cmd_item->valuestring;
                    char ack_buf[256];

                    if (strcmp(cmd, "open_door") == 0) {
                        /* 开门：继电器3模拟按键（IO改版：GPIO17） */
                        ESP_LOGI(TAG, "[EXEC #%d] open_door → 继电器3(GPIO17)吸合50ms→释放", seq);
                        door_open();
                        ESP_LOGI(TAG, "[HARDWARE #%d] 继电器3 已释放", seq);
                        snprintf(ack_buf, sizeof(ack_buf),
                            "{\"type\":\"ack\",\"cmd\":\"open_door\",\"status\":\"ok\",\"seq\":%d}\n", seq);
                        ESP_LOGI(TAG, "[SEND #%d] %s", seq, ack_buf);
                        tcp_client_send_data(ack_buf);
                    }
                    else if (strcmp(cmd, "close_door") == 0) {
                        /* 关门：继电器4模拟按键（IO改版：GPIO18） */
                        ESP_LOGI(TAG, "[EXEC #%d] close_door → 继电器4(GPIO18)吸合50ms→释放", seq);
                        door_close();
                        ESP_LOGI(TAG, "[HARDWARE #%d] 继电器4 已释放", seq);
                        snprintf(ack_buf, sizeof(ack_buf),
                            "{\"type\":\"ack\",\"cmd\":\"close_door\",\"status\":\"ok\",\"seq\":%d}\n", seq);
                        ESP_LOGI(TAG, "[SEND #%d] %s", seq, ack_buf);
                        tcp_client_send_data(ack_buf);
                    }
                    else if (strcmp(cmd, "go_floor") == 0) {
                        /* 去指定楼层：红外NEC发射（异步执行，避免阻塞recv循环导致TCP断连） */
                        cJSON *floor_item = cJSON_GetObjectItem(root, "floor");
                        if (floor_item != NULL && cJSON_IsNumber(floor_item)) {
                            uint8_t floor = (uint8_t)floor_item->valueint;
                            int step = (floor > Floor_Num) ? (floor - Floor_Num) : (Floor_Num - floor);
                            ESP_LOGI(TAG, "[EXEC #%d] go_floor(%d) → 当前楼层=%d, 预计移动%d层", seq, floor, Floor_Num, step);
                            /* 先回传ACK（避免后端超时） */
                            snprintf(ack_buf, sizeof(ack_buf),
                                "{\"type\":\"ack\",\"cmd\":\"go_floor\",\"status\":\"ok\",\"floor\":%d,\"seq\":%d}\n", floor, seq);
                            ESP_LOGI(TAG, "[SEND #%d] %s", seq, ack_buf);
                            tcp_client_send_data(ack_buf);
                            /* 异步执行楼层移动（独立任务，不阻塞recv循环，避免TCP断连） */
                            request_go_floor(floor);
                            ESP_LOGI(TAG, "[HARDWARE #%d] 楼层移动已提交异步任务", seq);
                        } else {
                            ESP_LOGW(TAG, "[EXEC #%d] go_floor: 缺少floor参数", seq);
                            snprintf(ack_buf, sizeof(ack_buf),
                                "{\"type\":\"ack\",\"cmd\":\"go_floor\",\"status\":\"error\",\"msg\":\"missing floor\",\"seq\":%d}\n", seq);
                            tcp_client_send_data(ack_buf);
                        }
                    }
                    else if (strcmp(cmd, "power_on") == 0) {
                        /* 开机：继电器5持续吸合供电（方案A：串在供电回路，IO改版GPIO19） */
                        ESP_LOGI(TAG, "[EXEC #%d] power_on → 继电器5(GPIO19)持续吸合供电", seq);
                        power_on();
                        snprintf(ack_buf, sizeof(ack_buf),
                            "{\"type\":\"ack\",\"cmd\":\"power_on\",\"status\":\"ok\",\"power\":1,\"seq\":%d}\n", seq);
                        ESP_LOGI(TAG, "[SEND #%d] %s", seq, ack_buf);
                        tcp_client_send_data(ack_buf);
                    }
                    else if (strcmp(cmd, "power_off") == 0) {
                        /* 关机：继电器5释放断电 */
                        ESP_LOGI(TAG, "[EXEC #%d] power_off → 继电器5(GPIO19)释放断电", seq);
                        power_off();
                        snprintf(ack_buf, sizeof(ack_buf),
                            "{\"type\":\"ack\",\"cmd\":\"power_off\",\"status\":\"ok\",\"power\":0,\"seq\":%d}\n", seq);
                        ESP_LOGI(TAG, "[SEND #%d] %s", seq, ack_buf);
                        tcp_client_send_data(ack_buf);
                    }
                    else if (strcmp(cmd, "power") == 0) {
                        /* 电源切换：开→关 / 关→开（兼容旧命令，语义由短按改为切换） */
                        if (power_is_on()) {
                            ESP_LOGI(TAG, "[EXEC #%d] power(切换) → 当前开机, 执行关机", seq);
                            power_off();
                        } else {
                            ESP_LOGI(TAG, "[EXEC #%d] power(切换) → 当前关机, 执行开机", seq);
                            power_on();
                        }
                        snprintf(ack_buf, sizeof(ack_buf),
                            "{\"type\":\"ack\",\"cmd\":\"power\",\"status\":\"ok\",\"power\":%d,\"seq\":%d}\n",
                            power_is_on() ? 1 : 0, seq);
                        ESP_LOGI(TAG, "[SEND #%d] %s", seq, ack_buf);
                        tcp_client_send_data(ack_buf);
                    }
                    else if (strcmp(cmd, "status") == 0) {
                        /* 查询状态：当前楼层 + 电源状态 + DHT11温湿度 */
                        uint8_t temp = 0, humi = 0;
                        dht11_read_data(&temp, &humi);
                        ESP_LOGI(TAG, "[EXEC #%d] status → 楼层=%d, 电源=%s, DHT11: temp=%d°C, humi=%d%%",
                            seq, Floor_Num, power_is_on() ? "开机" : "关机", temp, humi);
                        snprintf(ack_buf, sizeof(ack_buf),
                            "{\"type\":\"ack\",\"cmd\":\"status\",\"status\":\"ok\",\"floor\":%d,\"power\":%d,\"temp\":%d,\"humi\":%d,\"seq\":%d}\n",
                            Floor_Num, power_is_on() ? 1 : 0, temp, humi, seq);
                        ESP_LOGI(TAG, "[SEND #%d] %s", seq, ack_buf);
                        tcp_client_send_data(ack_buf);
                    }
                    else {
                        ESP_LOGW(TAG, "[EXEC #%d] 未知命令: %s", seq, cmd);
                        snprintf(ack_buf, sizeof(ack_buf),
                            "{\"type\":\"ack\",\"cmd\":\"%s\",\"status\":\"unknown\",\"seq\":%d}\n", cmd, seq);
                        tcp_client_send_data(ack_buf);
                    }
                }
                cJSON_Delete(root);
            } else {
                ESP_LOGW(TAG, "[RECV] JSON解析失败: %s", rx_buffer);
            }
        }        
    }
    vTaskDelete(NULL);
    ESP_LOGI(TAG,"QUIT TCP_CLIENT_TASK\n");
}

/**
 * 保存主控机传来的控制量
 */

// 保存状态
void save_state(void)
{
    nvs_handle_t handle;
    nvs_open("device_state", NVS_READWRITE, &handle);
    // nvs_set_u8(handle, "light", lightState);
    // nvs_set_u8(handle, "fan", fanState);
    nvs_commit(handle);
    nvs_close(handle);
}

// // 读取状态
// void load_state(void)
// {
//     nvs_handle_t handle;
//     nvs_open("device_state", NVS_READWRITE, &handle);
//     nvs_get_u8(handle, "light", &lightState);
//     nvs_get_u8(handle, "fan", &fanState);
//     nvs_close(handle);
// } 