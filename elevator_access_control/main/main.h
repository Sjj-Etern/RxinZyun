#ifndef __MAIN_H
#define __MAIN_H

#include "freertos/semphr.h"     // 互斥锁
    // ==================== 3. 定义 data 变量（你问的就是这个！） ====================
    sensor_data_t envdata={0};  // 在这里定义！
    SemaphoreHandle_t data_mutex;      // 互斥量句柄
    SemaphoreHandle_t spi_mutex;       // spi 互斥锁 
    SemaphoreHandle_t tcp_mutex;       // tcp 互斥锁 
#endif