// -------------设置读取继电器状态-----------------
#include "relay.h"
// #include <string.h>

// 定义你所有的继电器引脚
static const gpio_num_t relay_gpio_list[] = {
    GPIO_NUM_9,     // 继电器1  → 楼层按钮（3楼）
    GPIO_NUM_10,    // 继电器2  → 楼层按钮（5楼）
    GPIO_NUM_3,     // 继电器3  → 开门键
    GPIO_NUM_13,    // 继电器4  → 关门键
};
static bool relay_state_list[]={0,0,0,0};

// 计算继电器数量
#define RELAY_COUNT    (sizeof(relay_gpio_list) / sizeof(gpio_num_t))
#define RELAY_ON  1     // 高电平触发
#define RELAY_OFF 0     // 低电平关闭

// 初始化所有继电器
void relay_init_all(void)
{
    // 批量配置 GPIO
    gpio_config_t gpio_conf = {
        .pin_bit_mask = 0,
        .mode = GPIO_MODE_OUTPUT,         // 输出模式
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };

    // 把所有继电器引脚加入掩码
    for (int i = 0; i < RELAY_COUNT; i++) {
        gpio_conf.pin_bit_mask |= (1ULL << relay_gpio_list[i]);
    }

    // 一次初始化所有引脚
    gpio_config(&gpio_conf);

    // 默认全部关闭（高电平）
    for (int i = 0; i < RELAY_COUNT; i++) {
        gpio_set_level(relay_gpio_list[i], RELAY_OFF);
        relay_state_list[i] = 0;
    }
}

// 打开指定继电器（num: 1~4）
void relay_on(int num)
{
    if (num < 1 || num > RELAY_COUNT) return;
    gpio_set_level(relay_gpio_list[num - 1], RELAY_ON);  // 高电平吸合
    relay_state_list[num-1] = 1;
}

// 关闭指定继电器
void relay_off(int num)
{
    if (num < 1 || num > RELAY_COUNT) return;
    gpio_set_level(relay_gpio_list[num - 1], RELAY_OFF);  // 低电平断开
    relay_state_list[num-1] = 0;
}

/**
 * 读取继电器控制引脚状态
 * @param num:继电器
 *
*/ 
bool relay_is_on(int num)// 判断继电器是否打开
{
    // 先判断编号是否有效
    if (num < 1 || num > RELAY_COUNT) return false;
    return relay_state_list[num-1];
}
