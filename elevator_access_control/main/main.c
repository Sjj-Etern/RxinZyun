/**
 ****************************************************************************************************
 * @file        main.c
 * @author      正点原子团队(ALIENTEK)
 * @version     V1.0
 * @date        2023-08-26
 * @brief       RMT红外发送实验
 * @license     Copyright (c) 2020-2032, 广州市星翼电子科技有限公司
 ****************************************************************************************************
 * @attention
 *
 * 实验平台:正点原子 ESP32-S3 开发板
 * 在线视频:www.yuanzige.com
 * 技术论坛:www.openedv.com
 * 公司网址:www.alientek.com
 * 购买地址:openedv.taobao.com
 *
 ****************************************************************************************************
 */

#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/gpio.h"
#include "nvs_flash.h"
#include "esp_log.h"
#include "led.h"
#include "lcd.h"
#include "xl9555.h"
#include "emission.h"

#include "udp_broadcast.h"
#include "tcp_client.h"
#include "main.h"
#include "dht11.h"
#include "wifi_.h"
#include "relay.h"

#define TAG "MAIN"
#define SAMPLE_INTERVAL_TICKS  pdMS_TO_TICKS(5000)  // 采样间隔：5000ms
i2c_obj_t i2c0_master;

/**
 * 模拟梯控
 * 
 */    
void EA_Demo(uint8_t f){    
    uint8_t relayn=1;
    char buf[512];           
    extern uint8_t Floor_Num;    

    if (Floor_Num == f) return;

    switch (f){
        case  3:
            relayn=1;
            break;
        case  5:
            relayn=2;
            break;
        default:
            return;
            break;
    }

    // 去指定楼层（f楼）
    sprintf(buf,"%d -> %d",Floor_Num,f);
    if (xSemaphoreTake(spi_mutex, portMAX_DELAY) == pdTRUE){    // LCD屏显加锁
        lcd_show_string(30+50,  90, 200, 16, 16, buf, BLUE);
        xSemaphoreGive(spi_mutex); // 释放锁
    }

    ESP_LOGI("\n\nDEMO","Relay:%d, From: %d, To: %d",relayn, Floor_Num, f);
    relay_on(relayn);   // 梯控按下    
    vTaskDelay(50);    
    relay_off(relayn);  // 梯控按钮释放
    toFloor(f);         // 发送红外信号
}

// ======================= 温、湿度环境量采集 =====================
/**
 * 环境量检测线程
 */
void env_watch_thread(void *param){
    uint8_t temperature;
    uint8_t humidity;
    char buf[512];

    UBaseType_t uxHighWaterMark;    // 统计堆栈使用情况
    // sensor_data_t tmpdata={0};
    // extern sensor_data_t envdata;
    TickType_t last_tick=0;

    while(1){        
        // 0. 获取当前系统 tick
        TickType_t now_tick = xTaskGetTickCount();

        if(now_tick - last_tick < 15000){
            // lcd显示进度信息
            // show_process(x,5);          
            
            vTaskDelay(pdMS_TO_TICKS(1000));
            continue;
        }    
           
        // last_tick = now_tick;

        /* ------------------- 环境数据采集 -----------------*/        
        // 1.1 温度、湿度值采样     
        if(! dht11_read_data(&temperature, &humidity)){               /* 读取温湿度值 */                  

            if (xSemaphoreTake(spi_mutex, portMAX_DELAY) == pdTRUE){    // LCD屏显加锁
                sprintf(buf,"%d C",temperature);
                lcd_show_string(30+50,  50, 200, 16, 16, buf, BLUE);/* 显示温度 */

                sprintf(buf,"%d %%",humidity);
                lcd_show_string(30+50,  70, 200, 16, 16, buf, BLUE);/* 显示湿度 */

                sprintf(buf,"%d",Floor_Num);
                lcd_show_string(30+50,  90, 200, 16, 16, buf, BLUE);/* 显示楼层 */

                xSemaphoreGive(spi_mutex); // 释放锁
            }
            // if(tcp_client_is_connected()){
            //     char buf[512];
                        
            //     sprintf(buf,"{\"nodeid\":\"%s\",\"temp\":%d,\"humi\":%d}",
            //         "NODE_ID",
            //         temperature,
            //         humidity );
            //     // ESP_LOGI("ENV_WATCH_THREAD","SEND buf length:%d",sizeof(buf));
            //     tcp_client_send_data(buf);
            // }
        }
        
        // ----------- 模拟梯控（已禁用，改为TCP手动控制）------------
        // f = (f == 5) ? 3 : 5;
        // printf("\n\nto floor: %d\n",f);        
        // EA_Demo(f);
        // ---------------------------------
        uxHighWaterMark = uxTaskGetStackHighWaterMark(NULL);
        ESP_LOGI("STACK", "Remaining stack = %lu words", uxHighWaterMark);  // 堆栈使用情况
        // vTaskDelay(pdMS_TO_TICKS(1000));    


        now_tick = xTaskGetTickCount();
        last_tick = now_tick;
    }
    printf("\n exit  env_watch_thread()");
}

// ======================= 环境初始化 ============================
/** 
 * 环境初始化
 */
void app_init(void){
    // ---------------- 变量定义 -----------------
    esp_err_t ret;  
    i2c_obj_t i2c0_master;

    data_mutex = xSemaphoreCreateMutex();   // 初始化互斥锁
    if (data_mutex == NULL) {
        ESP_LOGE("MAIN", "Failed to create data_mutex");
        return;
    }
    spi_mutex = xSemaphoreCreateMutex();    // spi 互斥锁（多线程写lcd避免冲突）
    if (spi_mutex == NULL) {
        ESP_LOGE("MAIN", "Failed to create spi_mutex");
        return;
    }
    tcp_mutex  = xSemaphoreCreateMutex();   // tcp 操作互斥锁
    if (tcp_mutex == NULL) {
        ESP_LOGE("MAIN", "Failed to create tcp_mutex");
        return;
    }

    // ---------------- 初始化 -------------------
    ret = nvs_flash_init();             /* 初始化 NVS  */
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND){
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }

    led_init();                         /* 初始化LED */
    i2c0_master = iic_init(I2C_NUM_0);  /* 初始化IIC0 */
    spi2_init();                        /* 初始化SPI2 */
    xl9555_init(i2c0_master);           /* IO扩展芯片初始化 */
    lcd_init();                         /* 初始化LCD */

    // buzzer_init();          //  蜂鸣器初始化

    new_emission_init();                /* 初始化REMOTE */    
    uint8_t err = dht11_init();                 /* 初始化DHT11数字温湿度传感器 */
    relay_init_all();               //  继电器初始化  

    // --------------- WIFI 初始化 ----------------------------
    wifi_sta_init();    // 初始化并连接wifi
    udp_broadcast_start();  // udp广播配置（保留作为备选发现）
    tcp_client_set_server(ELEVATOR_SERVER_IP, TCP_PORT);  // 固定后端IP直连TCP，跳过UDP发现
    tcp_client_start();     // 启动tcp
    floor_move_task_start();  // 启动楼层移动独立任务（异步执行toFloor，避免阻塞TCP）
}


// ============================================================
/**
 * @brief       程序入口
 * @param       无
 * @retval      无
 */
void app_main(void)
{
    // ---------------- 变量定义 -----------------
    TickType_t last_sample_tick = 0;    // 保存【最后一次采样的时间】
    WIFI_INFO_T mywifi;                 // 当前WiFi信息结构

    // =================================
    app_init();             // 执行环境初始化操作    
    // buzzer_beep();          // 蜂鸣器嘀两声，进入环境监测

    lcd_show_string(30,  50, 200, 16, 16, "Temp:", RED);
    lcd_show_string(30,  70, 200, 16, 16, "Humi:", RED);
    lcd_show_string(30,  90, 200, 16, 16, "Floor:", RED);

    // 创建环境信息循环检测线程，内部有LCD 屏显互斥锁
    xTaskCreate(env_watch_thread,"env_watching",4096,NULL,5,NULL);  // 堆栈空间1012Words

    while (1)
    {   
        // 1. 获取当前系统 tick
        TickType_t now_tick = xTaskGetTickCount();
        // 2. 判断：距离上次采样是否超过间隔 默认5秒检测一次
        if( (now_tick - last_sample_tick) >= SAMPLE_INTERVAL_TICKS ){
            mywifi = check_network_status();
            // char buf[10];
            switch (mywifi.nWiFi){
                case 0:
                    // say_msg("No Wi-Fi.");
                    break;
                case 1:
                    // say_msg("To Wi-Fi...");
                    break;
                case 2:
                    // snprintf(buf,sizeof(buf),"rssi:%-3d",mywifi.rssi);
                    // say_msg(buf);
                    
                    // 绘制wifi信号
                    if(xSemaphoreTake(spi_mutex, portMAX_DELAY)==pdTRUE){
                        // lcd_draw_rssi(308,12,mywifi.rssi);
                        xSemaphoreGive(spi_mutex);
                    }

                    // listen_broadcast(); // 侦听广播信息
                    if(!tcp_client_is_connected()){
                        // ESP_LOGW(TAG, "TCP disconnected, re-udp_broadcast_start...");
                        // udp_broadcast_start();
                        ESP_LOGW(TAG, "TCP disconnected, re-discovering...");
                        udp_broadcast_send_discovery();
                    }
                    // else{
                        // ESP_LOGI(TAG,"TCP Connected.");
                    // }
                    break;
                default:
                    break;
            }
            
            last_sample_tick = now_tick;
        }

        LED_TOGGLE();   // LED 闪烁                
        vTaskDelay(pdMS_TO_TICKS(500)); // 延时 500 毫秒（真正稳定、通用）
    }
}
