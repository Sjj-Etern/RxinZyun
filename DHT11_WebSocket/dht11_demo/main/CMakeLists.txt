idf_component_register(
    SRCS
        "main.c"
        "wifi.c"
        "ws_client.c"

    INCLUDE_DIRS
        "."

    REQUIRES
        dht11
        esp_wifi
        esp_event
        esp_netif
        nvs_flash
        esp_websocket_client
        esp_timer
)
