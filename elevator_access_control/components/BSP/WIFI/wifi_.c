#include "wifi_.h"


/* 事件标志 */
EventGroupHandle_t   wifi_event;
const char *TAG = "static_ip";


/**
 * 
 */
/* 获取信号强度 */
// int wifi_get_rssi(void)
// {
//     // if (!g_wifi_connected) return -99;
//     int g_current_rssi =0;
//     wifi_ap_record_t ap_info;
//     if (esp_wifi_sta_get_ap_info(&ap_info) == ESP_OK)
//     {
//         g_current_rssi = ap_info.rssi;
//     }
//     return g_current_rssi;
// }

/**
 * @date 2026-05-24
 * @brief 在窗口最下面显示提示信息
 * @param s:显示的信息
 * @return void
 */
// void show_msg(char *s){
//     // lcd_fill(0,202,359,239,LIGHTGREEN);
//     // lcd_show_string(10,203,320,16,16,s,BLACK,WHITE);
//     // char buf[29];
//     // snprintf(buf, sizeof(buf), "%-28s", s);
//     // lcd_show_chinese(6,220,16,buf,GRAY,BLACK);
// }

/**
 * 可以获取Wi-Fi状态：未连接、正在连接、已经连接（ip地址、子网掩码、网关）
 */
// 2026-05-22
// 在程序的任何地方，都可以通过以下代码获取当前状态 
// void check_network_status(void) {
WIFI_INFO_T check_network_status(void) {    
    // char buf[50];
    WIFI_INFO_T wf_inf;
    esp_netif_ip_info_t ip_info;
    // 获取默认 Station 接口的 IP 信息
    esp_netif_t *netif = esp_netif_get_handle_from_ifkey("WIFI_STA_DEF");
    
    if (netif != NULL && esp_netif_get_ip_info(netif, &ip_info) == ESP_OK) {
        wf_inf.nWiFi = 1;   //有wifi
        wf_inf.rssi = -99;  // 信号初始值设置为弱

        // 检查获取到的 IP 是否有效（非 0.0.0.0）
        if (ip_info.ip.addr != 0) {
            // printf("网络已连接！当前 IP 地址: " IPSTR "\n", IP2STR(&ip_info.ip));            
            // // 正确：把 IP 转成字符串
            // sprintf(buf, "WiFi IP:%u.%u.%u.%u\n", IP2STR(&ip_info.ip));   // IP
            // printf(buf);
            // // show_msg(buf);
            // // lcd_show_string(2,100,160,16,16,buf,BLACK,WHITE);
            // sprintf(buf, "WiFi IP:%u.%u.%u.%u\n", IP2STR(&ip_info.netmask)); // 子网掩码
            // printf(buf);
            // // lcd_show_string(2,120,160,16,16,buf,BLACK,WHITE);
            // sprintf(buf, "WiFi IP:%u.%u.%u.%u\n", IP2STR(&ip_info.gw));   // 网关
            // // lcd_show_string(2,140,160,16,16,buf,BLACK,WHITE);
            // printf(buf);

            wf_inf.nWiFi = 2; // 已经连接
            // 把 IP 地址 格式化 → 存入数组
            sprintf(wf_inf.ipv4,   IPSTR, IP2STR(&ip_info.ip));
            sprintf(wf_inf.mask, IPSTR, IP2STR(&ip_info.netmask));
            sprintf(wf_inf.gw,   IPSTR, IP2STR(&ip_info.gw));
            
        } else {
            printf("正在获取 IP 地址...\n");            
            // show_msg("Getting IP ...");
        }
        // 当前已经连接（或正在连接）WIFI，
        // 获取信号强度（优：0~-50dBm，良：-50~-70dBm，一般：-70~-80dBm，差：-80~-100）
        int g_current_rssi =0;
        wifi_ap_record_t ap_info;
        if (esp_wifi_sta_get_ap_info(&ap_info) == ESP_OK)
        {
            g_current_rssi = ap_info.rssi;
            // ESP_LOGI("WIFI-INFO","rssi:%d",g_current_rssi);  
            wf_inf.rssi = g_current_rssi; // 信号强度
        }

    } else {
        printf("网络未连接或接口未找到\n");
        // show_msg("Not found Wi-Fi or port.");
        wf_inf.nWiFi = 0;   // 无WiFi
    }
    return wf_inf;
}

/**
 * @brief       链接显示
 * @param       flag:2->链接;1->链接失败;0->再链接中
 * @retval      无
 */
void connet_display(uint8_t flag)
{           
    if(flag == 2)
    {   
        char lcd_buff[100] = {0};
        sprintf(lcd_buff, "To WiFi:%s",DEFAULT_SSID);        
        // show_msg(lcd_buff);
    }
    else if (flag == 1)
    {
        // show_msg("wifi connecting fail");
    }
    else
    {
        // show_msg("wifi connecting......");
    }
}

/**
 * @brief       WIFI链接糊掉函数
 * @param       arg:传入网卡控制块
 * @param       event_base:WIFI事件
 * @param       event_id:事件ID
 * @param       event_data:事件数据
 * @retval      无
 */
static void wifi_event_handler(void *arg, esp_event_base_t event_base, int32_t event_id, void *event_data)
{
    static int s_retry_num = 0;
    // char buf[50];

    /* 扫描到要连接的WIFI事件 */
    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_START)
    {
        connet_display(0);
        esp_wifi_connect();
    }
    /* 连接WIFI事件 */
    else if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_CONNECTED)
    {
        connet_display(2);
    }
    /* 连接WIFI失败事件 */
    else if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_DISCONNECTED)
    {
        /* 尝试连接 */
        if (s_retry_num < 20)
        {
            esp_wifi_connect();
            s_retry_num++;
            ESP_LOGI(TAG, "retry to connect to the AP");
        }
        else
        {
            xEventGroupSetBits(wifi_event, WIFI_FAIL_BIT);
        }

        ESP_LOGI(TAG,"connect to the AP fail");
    }
    /* 工作站从连接的AP获得IP */
    else if(event_base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP)
    {
        ip_event_got_ip_t* event = (ip_event_got_ip_t*) event_data;
        ESP_LOGI(TAG, "static ip:" IPSTR, IP2STR(&event->ip_info.ip));
        
        s_retry_num = 0;
        xEventGroupSetBits(wifi_event, WIFI_CONNECTED_BIT);

        // sprintf(buf, "static IP:%u.%u.%u.%u", IP2STR(&event->ip_info.ip));
        // show_msg(buf);
    }
}

/**
 * @brief       WIFI初始化
 * @param       无
 * @retval      无
 */
void wifi_sta_init(void)
{
    static esp_netif_t *sta_netif = NULL;
    wifi_event= xEventGroupCreate();    /* 创建一个事件标志组 */
    /* 网卡初始化 */
    ESP_ERROR_CHECK(esp_netif_init());
    /* 创建新的事件循环 */
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    sta_netif= esp_netif_create_default_wifi_sta();
    assert(sta_netif);
    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK( esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, &wifi_event_handler, NULL) );
    ESP_ERROR_CHECK( esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, &wifi_event_handler, NULL) );
    ESP_ERROR_CHECK(esp_wifi_init(&cfg)); 

    wifi_config_t  wifi_config = WIFICONFIG(); 
    // -----------
    // wifi_config.sta.ssid= DEFAULT_SSID;
    char *ssid = DEFAULT_SSID;
    strncpy((char *)wifi_config.sta.ssid, ssid, sizeof(wifi_config.sta.ssid)-1);
    // wifi_config.sta.password = DEFAULT_PWD;
    if (DEFAULT_PWD == NULL || strlen(DEFAULT_PWD)==0){        
        wifi_config.sta.threshold.authmode=WIFI_AUTH_OPEN;
        memset(wifi_config.sta.password, 0, sizeof(wifi_config.sta.password));  // 密码区域清0
        ESP_LOGI("WIFI_STA_INIT","wifi no password");
    }else{
        // wifi_config.sta.password = DEFAULT_PWD;
        char *password = DEFAULT_PWD;
        strncpy((char *)wifi_config.sta.password, password, sizeof(wifi_config.sta.password)-1);
        wifi_config.sta.threshold.authmode = WIFI_AUTH_WPA2_PSK;
        ESP_LOGI("WIFI_STA_INIT","wifi password:%s",DEFAULT_PWD);
    }
    // -------------
    // 无密码时，memset(wifi_cfg.sta.password, 0, sizeof(wifi_cfg.sta.password));
    // wifi_cfg.sta.threshold.authmode = WIFI_AUTH_OPEN;
    // 有秘密时：
    // sta.threshold.authmode = WIFI_AUTH_WPA2_PSK;
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK( esp_wifi_set_config(ESP_IF_WIFI_STA, &wifi_config) );
    ESP_ERROR_CHECK(esp_wifi_start());

    /* 等待链接成功后、ip生成 */
    EventBits_t bits = xEventGroupWaitBits(wifi_event,
            WIFI_CONNECTED_BIT | WIFI_FAIL_BIT,
            pdFALSE,
            pdFALSE,
            portMAX_DELAY);

    /* 判断连接事件 */
    if (bits & WIFI_CONNECTED_BIT)
    {
        ESP_LOGI(TAG, "connected to ap SSID:%s password:%s",
                 DEFAULT_SSID, DEFAULT_PWD);
    }
    else if (bits & WIFI_FAIL_BIT)
    {
        // connet_display(1);
        ESP_LOGI(TAG, "Failed to connect to SSID:%s, password:%s",
                 DEFAULT_SSID, DEFAULT_PWD);
    }
    else
    {
        ESP_LOGE(TAG, "UNEXPECTED EVENT");
    }

    vEventGroupDelete(wifi_event);
}