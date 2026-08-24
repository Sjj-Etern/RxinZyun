/**
 ****************************************************************************************************
 * @file        emission.c
 * @author      正点原子团队(ALIENTEK)
 * @version     V1.0
 * @date        2023-08-26
 * @brief       RMT红外解码驱动代码
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

#include "emission.h"
#include "relay.h"

/* 保存NEC解码的地址和命令字节 */
uint16_t s_nec_code_address;
uint16_t s_nec_code_command;

QueueHandle_t receive_queue;
uint8_t tbuf[40];


static const uint16_t UP_KEY = 0xE619;      // 上键
static const uint16_t DOWN_KEY = 0XE718;    // 下键
static const uint16_t STOP_KEY = 0XBF40;    // 停止键
static const uint16_t ADDRESS = 0xFF00;     // 地址
static const uint16_t UP_STEP = 5000;       // 每层上用时ms
static const uint16_t DOWN_STEP = 4600;     // 每层下用时ms

uint8_t Floor_Num = 1;                       // 电梯初始位置（1楼）

rmt_channel_handle_t tx_channel = NULL;
rmt_encoder_handle_t nec_encoder = NULL;
rmt_transmit_config_t transmit_config = {
        .loop_count = 0,                                                                                                /* 0为不循环，-1为无限循环 */
    };


// =====================  电梯箱移动到指定楼层 ================    
/**
 * 初始楼层位 1楼
 * @nfloor: 目的楼层，1-5 
*/
void toFloor(uint8_t nFloor) {
    // 1. 有效性检查
    if (nFloor < 1 || nFloor > 5) {
        printf("[FLOOR] 无效的楼层：%d（有效范围：1-5）\n", nFloor);
        return;
    }
    if (nFloor == Floor_Num) {
        printf("[FLOOR] 我们已经到达目标楼层%d，无需再移动。\n", nFloor);
        return;
    }

    // 2. 有线继电器按钮模拟（先按下目标楼层按钮）
    int8_t relay = -1;
    switch (nFloor) {
        case 1: relay = 3; break;   // 1楼 → 继电器3（GPIO3）
        case 3: relay = 1; break;   // 3楼 → 继电器1（GPIO9）
        case 5: relay = 2; break;   // 5楼 → 继电器2（GPIO10）
        default: relay = -1; break; // 2楼暂未接线
    }
    printf("[FLOOR] 有线地板选择：%d->%d，继电器 = %d\n", Floor_Num, nFloor, relay);
    if (relay > 0) {
        relay_on(relay);
        vTaskDelay(pdMS_TO_TICKS(50));
        relay_off(relay);
        printf("[FLOOR] 继电器%d已通电50毫秒后释放\n", relay);
    } else {
        printf("[FLOOR] 地板%d没有连接的继电器，跳过按钮\n", nFloor);
    }

    // 3. 计算移动方向和步数
    uint8_t direction = (nFloor > Floor_Num) ? 1 : 2;  // 1上行，2下行
    uint8_t nStep = (nFloor > Floor_Num) ? (nFloor - Floor_Num) : (Floor_Num - nFloor);
    printf("[FLOOR] 楼层移动：%d -> %d，方向=%s，步数=%d\n",
           Floor_Num, nFloor, direction == 1 ? "上行" : "下行", nStep);

    // 4. 执行电梯移动
    Lift2UpDown(direction, nStep);

    // 5. 更新当前楼层（仅一次）
    Floor_Num = nFloor;
    printf("[FLOOR] 楼层移动完成。当前楼层 = %d\n", Floor_Num);
}





/* ===== 楼层移动独立任务（解决toFloor阻塞TCP recv循环导致连接断开问题）=====
 * 原问题：tcp_client_task在recv循环内同步调用toFloor，Lift2UpDown内vTaskDelay
 *         每层4850ms，跨楼层移动长达数秒~十秒，期间TCP任务无法recv，连接被
 *         异常重置(WinError 64 指定的网络名不再可用)，ESP被迫5秒重连。
 * 修复：toFloor放到独立任务异步执行，tcp_client收到go_floor后回ACK并通知本任务，
 *       recv循环立即继续，TCP连接保持不中断。 */
static TaskHandle_t s_floor_task_handle = NULL;
static volatile uint8_t s_target_floor = 0;

static void floor_move_task(void *arg)
{
    uint8_t target;
    while (1) {
        /* 阻塞等待楼层移动请求通知 */
        xTaskNotifyWait(0, 0xFFFFFFFF, NULL, portMAX_DELAY);
        target = s_target_floor;
        if (target >= 1 && target <= 5) {
            ESP_LOGI("FLOOR_TASK", "异步执行楼层移动 → %d楼", target);
            toFloor(target);
            ESP_LOGI("FLOOR_TASK", "楼层移动完成, 当前楼层=%d", Floor_Num);
        }
    }
}

/* 启动楼层移动独立任务（在app_init中调用一次） */
void floor_move_task_start(void)
{
    if (s_floor_task_handle == NULL) {
        xTaskCreate(floor_move_task, "floor_move", 4096, NULL, 5, &s_floor_task_handle);
    }
}

/* 异步请求楼层移动（非阻塞，供tcp_client任务调用） */
void request_go_floor(uint8_t floor)
{
    s_target_floor = floor;
    if (s_floor_task_handle != NULL) {
        xTaskNotifyGive(s_floor_task_handle);
    }
}


/* ===== 电梯门控制（继电器模拟按键）===== */

/**
 * 开门：继电器3吸合50ms后释放（模拟按下开门键）
 * 接线：继电器3 → 橙-棕白（开门线）
 */
void door_open(void){
    printf("[DOOR] 开门: 继电器3吸合 → ");
    relay_on(3);
    printf("ON(50ms) → ");
    vTaskDelay(pdMS_TO_TICKS(50));
    relay_off(3);
    printf("OFF → 完成\n");
}

/**
 * 关门：继电器4吸合50ms后释放（模拟按下关门键）
 * 接线：继电器4 → 黄-棕白（关门线）
 */
void door_close(void){
    printf("[DOOR] 关门: 继电器4吸合 → ");
    relay_on(4);
    printf("ON(50ms) → ");
    vTaskDelay(pdMS_TO_TICKS(50));
    relay_off(4);
    printf("OFF → 完成\n");
}
 

/** 
 * 初始化RMT供发射红外操作
 * tx_channel, nec_encoder, transmit_config
 */
void new_emission_init(void){
    /* 配置发送通道 */
    rmt_tx_channel_config_t tx_channel_cfg = {
        .clk_src = RMT_CLK_SRC_DEFAULT,                                                                                 /* RMT发送通道时钟源 */
        .resolution_hz = RMT_RESOLUTION_HZ,                                                                             /* RMT发送通道时钟分辨率 */
        .mem_block_symbols = 64,                                                                                        /* 通道一次可以存储的RMT符号数量 */
        .trans_queue_depth = 4,                                                                                         /* 允许在后台挂起的事务数，本例不会对多个事务进行排队，因此队列深度>1就足够了 */
        .gpio_num = RMT_TX_PIN,                                                                                         /* RMT发送通道引脚 */
    };
    // rmt_channel_handle_t tx_channel = NULL;
    ESP_ERROR_CHECK(rmt_new_tx_channel(&tx_channel_cfg, &tx_channel));                                                  /* 创建一个RMT发送通道 */

    /* 配置载波与占空比s */
    rmt_carrier_config_t carrier_cfg = {
        .frequency_hz = 38000,                                                                                          /* 载波频率，0表示禁用载波 */
        .duty_cycle = 0.33,                                                                                             /* 载波占空比 */
    };
    ESP_ERROR_CHECK(rmt_apply_carrier(tx_channel, &carrier_cfg));                                                       /* 对发送信道应用调制功能 */

    /* 不会在循环中发送NEC帧 */
    // rmt_transmit_config_t transmit_config = {
    //     .loop_count = 0,                                                                                                /* 0为不循环，-1为无限循环 */
    // };

    /* 配置编码器 */
    ir_nec_encoder_config_t nec_encoder_cfg = {
        .resolution = RMT_RESOLUTION_HZ,                                                                                /* 编码器分辨率 */
    };
    // rmt_encoder_handle_t nec_encoder = NULL;
    ESP_ERROR_CHECK(rmt_new_ir_nec_encoder(&nec_encoder_cfg, &nec_encoder));                                            /* 配置编码器 */

    /* 使能发送通道 */
    ESP_ERROR_CHECK(rmt_enable(tx_channel)); 
}


/**
 * @brief       初始化RMT
 * @param       无
 * @retval      无
 */
void emission_init(void)
{
    uint8_t t = 0;

    /* 配置接收通道 */
    rmt_rx_channel_config_t rx_channel_cfg = {
        .clk_src = RMT_CLK_SRC_DEFAULT,                                                                                 /* RMT接收通道时钟源 */
        .resolution_hz = RMT_RESOLUTION_HZ,                                                                             /* RMT接收通道时钟分辨率 */
        .mem_block_symbols = 64,                                                                                        /* 通道一次可以存储的RMT符号数量 */
        .gpio_num = RMT_RX_PIN,                                                                                         /* RMT接收通道引脚 */
    };
    rmt_channel_handle_t rx_channel = NULL;
    ESP_ERROR_CHECK(rmt_new_rx_channel(&rx_channel_cfg, &rx_channel));                                                  /* 创建一个RMT接收通道 */

    /* 创建消息队列，接收红外编码 */
    QueueHandle_t receive_queue = xQueueCreate(1, sizeof(rmt_rx_done_event_data_t));                                    /* 定义一个消息队列，用以处理RMT接收的回调函数 */
    assert(receive_queue);
    rmt_rx_event_callbacks_t cbs = {
        .on_recv_done = RMT_Rx_Done_Callback,                                                                           /* 事件回调，当一个RMT通道接收事务完成时调用 */
    };
    /* 注册红外回调函数 */
    ESP_ERROR_CHECK(rmt_rx_register_event_callbacks(rx_channel, &cbs, receive_queue));                                  /* 为RMT RX信道设置回调 */

    /* 以下时间要求基于NEC协议 */
    rmt_receive_config_t receive_config = {
        .signal_range_min_ns = 1250,                                                                                    /* NEC信号的最短持续时间为560us，1250ns＜560us，有效信号不会被视为噪声 */
        .signal_range_max_ns = 12000000,                                                                                /* NEC信号的最长持续时间为9000us，12000000ns>9000us，接收不会提前停止 */
    };

    /* 配置发送通道 */
    rmt_tx_channel_config_t tx_channel_cfg = {
        .clk_src = RMT_CLK_SRC_DEFAULT,                                                                                 /* RMT发送通道时钟源 */
        .resolution_hz = RMT_RESOLUTION_HZ,                                                                             /* RMT发送通道时钟分辨率 */
        .mem_block_symbols = 64,                                                                                        /* 通道一次可以存储的RMT符号数量 */
        .trans_queue_depth = 4,                                                                                         /* 允许在后台挂起的事务数，本例不会对多个事务进行排队，因此队列深度>1就足够了 */
        .gpio_num = RMT_TX_PIN,                                                                                         /* RMT发送通道引脚 */
    };
    rmt_channel_handle_t tx_channel = NULL;
    ESP_ERROR_CHECK(rmt_new_tx_channel(&tx_channel_cfg, &tx_channel));                                                  /* 创建一个RMT发送通道 */

    /* 配置载波与占空比s */
    rmt_carrier_config_t carrier_cfg = {
        .frequency_hz = 38000,                                                                                          /* 载波频率，0表示禁用载波 */
        .duty_cycle = 0.33,                                                                                             /* 载波占空比 */
    };
    ESP_ERROR_CHECK(rmt_apply_carrier(tx_channel, &carrier_cfg));                                                       /* 对发送信道应用调制功能 */

    /* 不会在循环中发送NEC帧 */
    rmt_transmit_config_t transmit_config = {
        .loop_count = 0,                                                                                                /* 0为不循环，-1为无限循环 */
    };

    /* 配置编码器 */
    ir_nec_encoder_config_t nec_encoder_cfg = {
        .resolution = RMT_RESOLUTION_HZ,                                                                                /* 编码器分辨率 */
    };
    rmt_encoder_handle_t nec_encoder = NULL;
    ESP_ERROR_CHECK(rmt_new_ir_nec_encoder(&nec_encoder_cfg, &nec_encoder));                                            /* 配置编码器 */

    /* 使能发送、接收通道 */
    ESP_ERROR_CHECK(rmt_enable(tx_channel));                                                                            /* 使能发送通道 */
    ESP_ERROR_CHECK(rmt_enable(rx_channel));                                                                            /* 使能接收通道 */

    /* 保存接收到的RMT符号 */
    rmt_symbol_word_t raw_symbols[64];                                                                                  /* 64个符号对于标准NEC框架应该足够 */
    rmt_rx_done_event_data_t rx_data;

    ESP_ERROR_CHECK(rmt_receive(rx_channel, raw_symbols, sizeof(raw_symbols), &receive_config));                        /* 准备接收 */


    static uint16_t address = 65280;    // address FF00
    uint16_t cmd = 0;
    uint8_t dt[]={191,230,231};

    while (1)
    {
        if (xQueueReceive(receive_queue, &rx_data, pdMS_TO_TICKS(1000)) == pdPASS)                                      /* 等待RX完成信号 */
        {
            example_parse_nec_frame(rx_data.received_symbols, rx_data.num_symbols);                                     /* 解析接收符号并打印结果 */
            ESP_ERROR_CHECK(rmt_receive(rx_channel, raw_symbols, sizeof(raw_symbols), &receive_config));                /* 重新开始接收 */
        }
        else                                                                                                            /* 超时，传输预定义的IR NEC数据包 */
        {
            t++;    // uint8_t
            // if(t>2){
            //     t=1;
            // } 

            t =  t>2 ? 1 : 2;
            // uint16_t td = t == 1? 4850:4550;

            printf("\n\n t:%d",t);
            // ir_option(t,td, tx_channel, nec_encoder, transmit_config);
            


            cmd = ((uint16_t) dt[t]<<8) | ((uint8_t)~dt[t]);
            printf("\ncmd:%04X",cmd);

            const ir_nec_scan_code_t scan_code = {
                // .command = t,
                .command = cmd,
                .address = address,
            };

            lcd_fill(116, 110, 176, 150, WHITE);
            sprintf((char *)tbuf, "%d", scan_code.command);
            printf("TX KEYVAL = %d\n", scan_code.command);

            printf("\n\nSend IR:\nAddress: %04X, Command:%04X",scan_code.address,scan_code.command);
            printf("\nSend IR:\nAddress: %d, Command:%d",scan_code.address,scan_code.command);

            lcd_show_string(116, 110, 200, 16, 16, (char *)tbuf, BLUE);
            ESP_ERROR_CHECK(rmt_transmit(tx_channel, nec_encoder, &scan_code, sizeof(scan_code), &transmit_config));    /* 通过RMT发送信道传输数据 */
        }
        printf("ir_finished, delaytime...");
        vTaskDelay(pdMS_TO_TICKS(5000));    // 延时5秒
    }
}
/**
 * 电梯移动
 * @direction: 方向（1上、2下）
 * @step：层数
 */
void Lift2UpDown(uint8_t direction,uint8_t step){
    uint16_t cmd=0;
    uint16_t delaytime=0;

    if(step<1 || step>4){
        step=1;
    }

    switch (direction){
    case 1:
        /* code */
        cmd = UP_KEY;
        delaytime = UP_STEP * step;
        break;
    case 2:
        cmd=DOWN_KEY;
        delaytime = DOWN_STEP * step;
        break;
    default:
        return;
        break;
    }
    printf("\nDirection: %d, KeyVal: %04X, DelayTime: %d\n",direction, cmd, delaytime);
    ESP_LOGI("MOVE_STEP","command:%04X",cmd);

    ir_nec_scan_code_t scan_code = { //const                
                .command = cmd,
                .address = ADDRESS,
            };
    ESP_ERROR_CHECK(rmt_transmit(tx_channel, nec_encoder, &scan_code, sizeof(scan_code), &transmit_config));    
    vTaskDelay(pdMS_TO_TICKS(delaytime));    // 延时5秒
    
    // 发送停止信号    
    scan_code.command = STOP_KEY;
    scan_code.address = ADDRESS;
    // printf("\nStop moving...");
    ESP_ERROR_CHECK(rmt_transmit(tx_channel, nec_encoder, &scan_code, sizeof(scan_code), &transmit_config));   
    
    vTaskDelay(pdMS_TO_TICKS(50));    // 延时.05秒
    ESP_ERROR_CHECK(rmt_transmit(tx_channel, nec_encoder, &scan_code, sizeof(scan_code), &transmit_config));   
    
}

// /**
//  * 模拟红外遥控器
//  * @direction:1上 2下
//  */
// void ir_option(uint8_t direction, uint16_t delaytime, rmt_channel_handle_t tx_c, rmt_encoder_handle_t nec_ecd, rmt_transmit_config_t transmit_cfg){
//     static uint16_t UP_KEY = 0xE619;
//     static uint16_t DOWN_KEY = 0XE718;
//     static uint16_t STOP_KEY = 0XBF40;
//     static uint16_t ADDRESS = 0xFF00;
//     uint16_t cmd=0;

//     switch (direction)
//     {
//     case 1: // 上
//         /* code */
//         cmd = UP_KEY;
//         break;
//     case 2: // 下
//         cmd = DOWN_KEY;
//         break;
//     default:
//         return;
//         break;
//     }
//     printf("\nDirection: %d, KeyVal: %04X, DelayTime: %d",direction, cmd, delaytime);
//     ESP_LOGI("MOVE_STEP","command:%d",cmd);

//     ir_nec_scan_code_t scan_code = { //const                
//                 .command = cmd,
//                 .address = ADDRESS,
//             };
//     ESP_ERROR_CHECK(rmt_transmit(tx_c, nec_ecd, &scan_code, sizeof(scan_code), &transmit_cfg));    /* 通过RMT发送信道传输数据 */
//     vTaskDelay(pdMS_TO_TICKS(delaytime));    // 延时5秒
    
//     // 发送停止信号    
//     scan_code.command = STOP_KEY;
//     scan_code.address = ADDRESS;
//     printf("\nStop moving...");
//     // ESP_ERROR_CHECK(rmt_transmit(tx_channel, nec_encoder, &scan_code, sizeof(scan_code), &transmit_config));
//     ESP_ERROR_CHECK(rmt_transmit(tx_c, nec_ecd, &scan_code, sizeof(scan_code), &transmit_cfg));

// }


/**
 * @brief       判断数据时序长度是否在NEC时序时长容差范围内 正负 RMT_NEC_DECODE_MARGIN 的值以内
 * @param       无
 * @retval      无
 */
inline bool nec_check_in_range(uint32_t signal_duration, uint32_t spec_duration)
{
    return (signal_duration < (spec_duration + RMT_NEC_DECODE_MARGIN)) &&
           (signal_duration > (spec_duration - RMT_NEC_DECODE_MARGIN));
}

/**
 * @brief       对比数据时序长度判断是否为逻辑0
 * @param       无
 * @retval      无
 */
bool nec_parse_logic0(rmt_symbol_word_t *rmt_nec_symbols)
{
    return nec_check_in_range(rmt_nec_symbols->duration0, NEC_PAYLOAD_ZERO_DURATION_0) &&
           nec_check_in_range(rmt_nec_symbols->duration1, NEC_PAYLOAD_ZERO_DURATION_1);
}

/**
 * @brief       对比数据时序长度判断是否为逻辑1
 * @param       无
 * @retval      无
 */
bool nec_parse_logic1(rmt_symbol_word_t *rmt_nec_symbols)
{
    return nec_check_in_range(rmt_nec_symbols->duration0, NEC_PAYLOAD_ONE_DURATION_0) &&
           nec_check_in_range(rmt_nec_symbols->duration1, NEC_PAYLOAD_ONE_DURATION_1);
}

/**
 * @brief       将RMT接收结果解码出NEC地址和命令
 * @param       无
 * @retval      无
 */
bool nec_parse_frame(rmt_symbol_word_t *rmt_nec_symbols)
{
    rmt_symbol_word_t *cur = rmt_nec_symbols;
    uint16_t address = 0;
    uint16_t command = 0;

    bool valid_leading_code = nec_check_in_range(cur->duration0, NEC_LEADING_CODE_DURATION_0) &&
                              nec_check_in_range(cur->duration1, NEC_LEADING_CODE_DURATION_1);

    if (!valid_leading_code) 
    {
        return false;
    }

    cur++;

    for (int i = 0; i < 16; i++)
    {
        if (nec_parse_logic1(cur)) 
        {
            address |= 1 << i;
        } 
        else if (nec_parse_logic0(cur))
        {
            address &= ~(1 << i);
        } 
        else 
        {
            return false;
        }
        cur++;
    }

    for (int i = 0; i < 16; i++)
    {
        if (nec_parse_logic1(cur))
        {
            command |= 1 << i;
        }
        else if (nec_parse_logic0(cur))
        {
            command &= ~(1 << i);
        }
        else
        {
            return false;
        }
        cur++;
    }

    /* 保存数据地址和命令，用于判断重复按键 */
    s_nec_code_address = address;
    s_nec_code_command = command;

    printf("\n\n\nREC:\n address:%d (%04X),\n command: %d (%04X)", s_nec_code_address, s_nec_code_address, s_nec_code_command, s_nec_code_command);
    // printf("\n address:%04X",s_nec_code_address);

    return true;
}

/**
 * @brief       检查数据帧是否为重复按键：一直按住同一个键
 * @param       无
 * @retval      无
 */
bool nec_parse_frame_repeat(rmt_symbol_word_t *rmt_nec_symbols)
{
    return nec_check_in_range(rmt_nec_symbols->duration0, NEC_REPEAT_CODE_DURATION_0) &&
           nec_check_in_range(rmt_nec_symbols->duration1, NEC_REPEAT_CODE_DURATION_1);
}

/**
 * @brief       根据NEC编码解析红外协议并打印指令结果
 * @param       无
 * @retval      无
 */
void example_parse_nec_frame(rmt_symbol_word_t *rmt_nec_symbols, size_t symbol_num)
{
    switch (symbol_num) /* 解码RMT接收数据 */
    {
        case 34:        /* 正常NEC数据帧 */
        {
            if (nec_parse_frame(rmt_nec_symbols) )  // 可以获取address、command
            {
                lcd_fill(116, 130, 176, 150, WHITE);
                sprintf((char *)tbuf, "%d", s_nec_code_command);
                printf("RX KEYCNT = %d\n", s_nec_code_command);
                lcd_show_string(116, 130, 200, 16, 16, (char *)tbuf, BLUE);
            }
            break;
        }
        
        case 2:         /* 重复NEC数据帧 */
        {
            if (nec_parse_frame_repeat(rmt_nec_symbols))
            {
                printf("RX KEYCNT = %d, repeat\n", s_nec_code_command);
            }
            break;
        }

        default:        /* 未知NEC数据帧 */
        {
            printf("Unknown NEC frame\r\n\r\n");
            break;
        }
    }
}

/**
 * @brief       RMT数据接收完成回调函数
 * @param       无
 * @retval      无
 */
bool RMT_Rx_Done_Callback(rmt_channel_handle_t channel, const rmt_rx_done_event_data_t *edata, void *user_data)
{
    BaseType_t high_task_wakeup = pdFALSE;
    QueueHandle_t receive_queue = (QueueHandle_t)user_data;

    xQueueSendFromISR(receive_queue, edata, &high_task_wakeup); /* 将收到的RMT数据通过消息队列发送到解析任务 */
    return high_task_wakeup == pdTRUE;
}
