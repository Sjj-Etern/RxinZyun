#include "dht11.h"
#include "driver/gpio.h"
#include "esp_err.h"
#include "esp_rom_sys.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#define DHT11_TIMEOUT_US      100
#define DHT11_START_LOW_MS    20
#define DHT11_START_HIGH_US   30

static void gpio_output(gpio_num_t gpio){ gpio_set_direction(gpio, GPIO_MODE_OUTPUT_OD); }
static void gpio_input(gpio_num_t gpio){ gpio_set_direction(gpio, GPIO_MODE_INPUT); }
static inline void gpio_write(gpio_num_t gpio, uint32_t level){ gpio_set_level(gpio, level); }
static inline int gpio_read(gpio_num_t gpio){ return gpio_get_level(gpio); }

static esp_err_t wait_level(dht11_t *dev,uint32_t level,uint32_t timeout_us){
    while(timeout_us--){
        if(gpio_read(dev->gpio_num)==(int)level) return ESP_OK;
        esp_rom_delay_us(1);
    }
    return ESP_ERR_TIMEOUT;
}

static uint8_t read_bit(dht11_t *dev){
    if(wait_level(dev,0,DHT11_TIMEOUT_US)!=ESP_OK) return 0xFF;
    if(wait_level(dev,1,DHT11_TIMEOUT_US)!=ESP_OK) return 0xFF;
    esp_rom_delay_us(40);
    uint8_t b=gpio_read(dev->gpio_num);
    if(wait_level(dev,0,DHT11_TIMEOUT_US)!=ESP_OK) return 0xFF;
    return b;
}

static esp_err_t read_byte(dht11_t *dev,uint8_t *data){
    *data=0;
    for(int i=0;i<8;i++){
        uint8_t bit=read_bit(dev);
        if(bit==0xFF) return ESP_ERR_TIMEOUT;
        *data=(*data<<1)|bit;
    }
    return ESP_OK;
}

static esp_err_t dht11_start(dht11_t *dev){
    gpio_output(dev->gpio_num);
    gpio_write(dev->gpio_num,0);
    vTaskDelay(pdMS_TO_TICKS(DHT11_START_LOW_MS));
    gpio_write(dev->gpio_num,1);
    esp_rom_delay_us(DHT11_START_HIGH_US);
    gpio_input(dev->gpio_num);
    if(wait_level(dev,0,100)!=ESP_OK) return ESP_ERR_TIMEOUT;
    if(wait_level(dev,1,100)!=ESP_OK) return ESP_ERR_TIMEOUT;
    if(wait_level(dev,0,100)!=ESP_OK) return ESP_ERR_TIMEOUT;
    return ESP_OK;
}

esp_err_t dht11_init(dht11_t *dev,gpio_num_t gpio){
    if(!dev) return ESP_ERR_INVALID_ARG;
    dev->gpio_num=gpio;
    dev->humidity=0;
    dev->temperature=0;
    gpio_config_t cfg={
        .pin_bit_mask=1ULL<<gpio,
        .mode=GPIO_MODE_OUTPUT_OD,
        .pull_up_en=GPIO_PULLUP_ENABLE,
        .pull_down_en=GPIO_PULLDOWN_DISABLE,
        .intr_type=GPIO_INTR_DISABLE
    };
    esp_err_t ret = gpio_config(&cfg);
    if (ret != ESP_OK) {
        return ret;
    }
    gpio_set_level(gpio,1);
    return ESP_OK;
}

esp_err_t dht11_read(dht11_t *dev){
    if(!dev) return ESP_ERR_INVALID_ARG;
    uint8_t data[5]={0};
    if(dht11_start(dev)!=ESP_OK) return ESP_ERR_TIMEOUT;
    for(int i=0;i<5;i++){
        esp_err_t ret=read_byte(dev,&data[i]);
        if(ret!=ESP_OK) return ret;
    }
    if(((uint8_t)(data[0]+data[1]+data[2]+data[3]))!=data[4])
        return ESP_ERR_INVALID_CRC;
    dev->humidity=data[0];
    dev->temperature=data[2];
    return ESP_OK;
}
