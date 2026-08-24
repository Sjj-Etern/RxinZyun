#ifndef __WIFI_H_
#define __WIFI_H_

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/event_groups.h"
#include "esp_system.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include <netdb.h>
#include "lcd.h"

#include "esp_netif.h"
#include "lwip/ip_addr.h"
#include "cJSON.h"

// #include "lcd.h"
// #include "freertos/semphr.h"     // 互斥锁
    // ==================== 3. 定义 data 变量（你问的就是这个！） ====================
    extern sensor_data_t envdata;   //={0};  // 在这里定义！
    extern SemaphoreHandle_t data_mutex;      // 互斥量句柄
    extern SemaphoreHandle_t spi_mutex;       // spi 互斥锁 
    extern SemaphoreHandle_t tcp_mutex;       // tcp 互斥锁 

    // // 初始化 
    // spi_mutex = xSemaphoreCreateMutex();
    // xSemaphoreTake(spi_mutex, portMAX_DELAY);
    // ......
    // xSemaphoreGive(spi_mutex);

    // void env_watch_thread(void *param);


/* 链接wifi名称 仅2.4G */
#define DEFAULT_SSID       "Skills-iot" //"Skills-iot" //  "CMCC-u9kZ" // 链接wifi名称
#define DEFAULT_PWD        "12345678"  // "12345678"  // wifi密码 "

// #define BROADCAST_PORT 10832
// #define HOST_PORT      10833

#define UDP_PORT        10832
#define TCP_PORT        10833
#define BROADCAST_ADDR  "255.255.255.255"
#define NODE_ID         "node_001"   // 每个节点唯一，可编译时修改

/* 后端服务器固定IP：直连TCP跳过UDP发现（AP隔离/UDP发现收不到响应时使用）
   改成运行后端的电脑局域网IP（须与ESP32同网段，如ESP是192.168.1.110，后端是192.168.1.106） */
#define ELEVATOR_SERVER_IP   "192.168.51.12"

// /* 事件标志 */
#define WIFI_CONNECTED_BIT  BIT0
#define WIFI_FAIL_BIT       BIT1

/* WIFI默认配置 */
#define WIFICONFIG()   {                            \
    .sta = {                                        \
        .ssid = DEFAULT_SSID,                       \
        .password = DEFAULT_PWD,                    \
        .threshold.authmode = WIFI_AUTH_WPA2_PSK,   \
    },                                              \
}

// WiFi 信息，
// 获取信号强度（优：0 ~ -50dBm，良：-50 ~ -70dBm，一般：-70 ~ -80dBm，差：-80 ~ -100）
typedef struct{
    uint8_t nWiFi;      // 0: 无WIFI，1：正在连接，2：已经连接
    int rssi;           // 当nWiFi非 0 值时，返回信号强度
    char ipv4[16];    // 当nWiFi为 2 值时，返回网址信息
    char mask[16];
    char gw[16];
}WIFI_INFO_T;




void wifi_sta_init(void);
// void check_network_status(void);
WIFI_INFO_T check_network_status(void); // 获取wifi联网信息、信号强度及地址信息
// void show_msg(char *s);
// 获取当前 WiFi 信号强度 (RSSI)
// int wifi_get_rssi(void);
#endif